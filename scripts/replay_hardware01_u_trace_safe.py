#!/usr/bin/env python3
"""Safely replay an exact hardware01 u_real_order trace on the Aero Hand.

The trace is produced from sim rollout videos where the policy action is already
converted to hardware-style real order:
  [thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]

By default this is a dry run. Add --run only when the hand is powered, clear,
and you are ready to interrupt power if needed.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, DEFAULT_CALIBRATION_PATH, fmt, load_raw_rest  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402


DEFAULT_TRACE = (
    REPO_ROOT
    / "sim"
    / "hardware01_exact_rollout_trace_20260706"
    / "hardware01_rollout0_u_trace.json"
)
LOG_DIR = REPO_ROOT / "logs"
PRESETS = {
    "physics_id_rollout0_real_hand_fitted": {
        "description": (
            "Best operator-fitted real-hand open-loop replay as of 2026-07-09; "
            "PhysicsID rollout 0 with thumb reduced and index/middle/pinky support raised."
        ),
        "trace": REPO_ROOT
        / "sim"
        / "hardware01_real_calibrated_physics_id_trace_20260708"
        / "hardware01_physics_id_rollout0_u_trace.json",
        "playback_scale": 1.0,
        "channel_scale": "thumb_abd=0.90,thumb_flex=0.5,thumb_tendon=0.6,index=0.50,middle=0.7",
        "channel_bias": "thumb_abd=-0.04,thumb_flex=-0.32,thumb_tendon=-0.14,index=0.34,middle=0.12,pinky=0.04",
        "max_step_delta": 0.08,
        "sample_every": 5,
        "repeat": 5,
    },
}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def channel_index(label: str) -> int:
    normalized = label.strip().lower()
    if normalized.startswith("ch") and normalized[2:].isdigit():
        idx = int(normalized[2:])
    elif normalized.isdigit():
        idx = int(normalized)
    else:
        matches = [idx for idx, name in enumerate(CHANNEL_NAMES) if name.lower() == normalized]
        if not matches:
            raise ValueError(f"Unknown channel '{label}'. Valid names: {', '.join(CHANNEL_NAMES)}")
        idx = matches[0]
    if idx < 0 or idx >= len(CHANNEL_NAMES):
        raise ValueError(f"Channel index out of range: {label}")
    return idx


def parse_channel_values(spec: str | None, *, default: float) -> list[float]:
    values = [default] * len(CHANNEL_NAMES)
    if not spec:
        return values
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Expected name=value in '{item}'")
        name, raw_value = item.split("=", 1)
        value = float(raw_value)
        if name.strip().lower() in ("all", "default", "*"):
            values = [value] * len(CHANNEL_NAMES)
            continue
        values[channel_index(name)] = value
    return values


def load_trace(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise RuntimeError(f"Expected a list trace: {path}")
    rows = []
    for idx, row in enumerate(data):
        if "u_real_order" not in row:
            raise RuntimeError(f"Trace row missing u_real_order at row {idx}: {path}")
        target = [clamp01(v) for v in row["u_real_order"]]
        if len(target) != len(CHANNEL_NAMES):
            raise RuntimeError(f"Expected {len(CHANNEL_NAMES)} channels, got {len(target)} at row {idx}")
        rows.append({
            "step": int(row.get("step", idx)),
            "target": target,
            "raw_action": row.get("raw_action"),
            "done": bool(row.get("done", False)),
        })
    if not rows:
        raise RuntimeError(f"Trace is empty: {path}")
    return rows


def scale_target(
    target: list[float],
    playback_scale: float,
    center: float,
    channel_scale: list[float],
    channel_bias: list[float],
) -> list[float]:
    return [
        clamp01(center + playback_scale * channel_scale[idx] * (v - center) + channel_bias[idx])
        for idx, v in enumerate(target)
    ]


def cap_step(prev: list[float], target: list[float], max_delta: float) -> list[float]:
    if max_delta <= 0:
        return list(target)
    capped = []
    for old, new in zip(prev, target):
        delta = max(-max_delta, min(max_delta, new - old))
        capped.append(clamp01(old + delta))
    return capped


def enforce_safety(currents: list[float], temps: list[float], abort_current: float, abort_temp: float) -> None:
    current_hits = [
        f"{idx}:{name}={value:.1f}mA"
        for idx, (name, value) in enumerate(zip(CHANNEL_NAMES, currents))
        if abs(value) >= abort_current
    ]
    temp_hits = [
        f"{idx}:{name}={value:.1f}C"
        for idx, (name, value) in enumerate(zip(CHANNEL_NAMES, temps))
        if value >= abort_temp
    ]
    if current_hits or temp_hits:
        parts = []
        if current_hits:
            parts.append("current " + ", ".join(current_hits))
        if temp_hits:
            parts.append("temp " + ", ".join(temp_hits))
        raise RuntimeError("Safety abort: " + "; ".join(parts))


def write_log_header(writer: csv.DictWriter) -> None:
    writer.writeheader()


def log_row(writer: csv.DictWriter, step: int, elapsed_s: float, target: list[float],
            pos: list[float] | None, currents: list[float] | None, temps: list[float] | None) -> None:
    row: dict[str, float | int | str] = {"step": step, "elapsed_s": elapsed_s}
    for idx, name in enumerate(CHANNEL_NAMES):
        row[f"target_{idx}_{name}"] = target[idx]
        row[f"pos_{idx}_{name}"] = "" if pos is None else pos[idx]
        row[f"curr_ma_{idx}_{name}"] = "" if currents is None else currents[idx]
        row[f"temp_c_{idx}_{name}"] = "" if temps is None else temps[idx]
    writer.writerow(row)


def apply_preset(args: argparse.Namespace) -> None:
    if not args.preset:
        return
    preset = PRESETS[args.preset]
    for key, value in preset.items():
        if key == "description":
            continue
        setattr(args, key, value)


def print_presets() -> None:
    for name, preset in PRESETS.items():
        print(f"{name}: {preset['description']}")


def run(args: argparse.Namespace) -> int:
    if args.list_presets:
        print_presets()
        return 0
    apply_preset(args)
    rows = load_trace(args.trace)
    rows = rows[args.start_step:]
    if args.steps is not None:
        rows = rows[:args.steps]
    if not rows:
        raise RuntimeError("No rows selected after --start-step/--steps")

    channel_scale = parse_channel_values(args.channel_scale, default=1.0)
    channel_bias = parse_channel_values(args.channel_bias, default=0.0)

    selected = [
        {
            **row,
            "target": scale_target(
                row["target"],
                args.playback_scale,
                args.scale_center,
                channel_scale,
                channel_bias,
            ),
        }
        for row in rows
    ]
    if args.repeat < 1:
        raise RuntimeError("--repeat must be >= 1")
    if args.repeat > 1:
        base = selected
        selected = []
        for repeat_idx in range(args.repeat):
            for row in base:
                selected.append({**row, "repeat": repeat_idx})

    print(f"trace: {args.trace}")
    if args.preset:
        print(f"preset: {args.preset} - {PRESETS[args.preset]['description']}")
    print(f"selected_steps: {len(selected)} start_step={args.start_step}")
    if args.repeat > 1:
        print(f"repeat: {args.repeat} loops; duration ~= {len(selected) / args.rate:.1f}s")
    print(f"rate: {args.rate:.2f} Hz playback_scale={args.playback_scale:.3f} center={args.scale_center:.3f}")
    if args.channel_scale:
        print("channel_scale:", fmt(channel_scale))
    if args.channel_bias:
        print("channel_bias:", fmt(channel_bias))
    print(f"max_step_delta: {args.max_step_delta:.3f}; abort_current={args.abort_current:.1f}mA abort_temp={args.abort_temp:.1f}C")
    print("Trace summary:")
    targets_by_channel = list(zip(*(row["target"] for row in selected)))
    for idx, (name, vals) in enumerate(zip(CHANNEL_NAMES, targets_by_channel)):
        print(
            f"  ch{idx}:{name:13s} min={min(vals):.3f} max={max(vals):.3f} "
            f"span={max(vals)-min(vals):.3f}"
        )

    if not args.run:
        print("\nDry run only. Add --run to send these exact hardware01 u targets to the hand.")
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"hardware01_u_trace_replay_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fieldnames = ["step", "elapsed_s"]
    for idx, name in enumerate(CHANNEL_NAMES):
        fieldnames.extend([
            f"target_{idx}_{name}",
            f"pos_{idx}_{name}",
            f"curr_ma_{idx}_{name}",
            f"temp_c_{idx}_{name}",
        ])

    period = 1.0 / args.rate
    with AeroHandController(args.port, args.baud) as hand, log_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        write_log_header(writer)
        rest = load_raw_rest(args.calibration)
        prev = rest
        start = time.monotonic()
        try:
            if args.apply_rest_first:
                print("applying raw rest:", fmt(rest))
                hand.send_raw_actuators(rest)
                time.sleep(args.rest_settle)

            for idx, row in enumerate(selected):
                target = cap_step(prev, row["target"], args.max_step_delta)
                hand.send_raw_actuators(target)
                prev = target
                time.sleep(period)

                should_sample = idx % args.sample_every == 0 or idx == len(selected) - 1
                pos = curr = temp = None
                if should_sample:
                    pos = hand.get_pos_norm()
                    curr = hand.get_currents_ma()
                    temp = hand.get_temperatures_c()
                    enforce_safety(curr, temp, args.abort_current, args.abort_temp)
                    print(
                        f"[{idx:04d}] max_curr={max(abs(v) for v in curr):.1f}mA "
                        f"max_temp={max(temp):.1f}C target={fmt(target)} pos={fmt(pos)}"
                    )
                log_row(writer, idx, time.monotonic() - start, target, pos, curr, temp)
        except Exception:
            print("\n[recovery] sending raw rest after exception/abort")
            hand.send_raw_actuators(rest)
            time.sleep(args.rest_settle)
            raise
        else:
            if args.rest_after:
                print("[recovery] sending raw rest after replay")
                hand.send_raw_actuators(rest)
                time.sleep(args.rest_settle)

    print(f"\nReplay complete. Log: {log_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay exact hardware01 sim u trace on the real Aero Hand.")
    parser.add_argument("--preset", choices=sorted(PRESETS), help="Named trace/scale/bias package.")
    parser.add_argument("--list-presets", action="store_true")
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION_PATH)
    parser.add_argument("--start-step", type=int, default=0)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--repeat", type=int, default=1, help="Repeat the selected trace this many times without resting between loops.")
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--playback-scale", type=float, default=1.0, help="Scale around --scale-center; 1.0 is exact trace.")
    parser.add_argument("--scale-center", type=float, default=0.5)
    parser.add_argument("--channel-scale", help="Optional per-channel range scale, e.g. thumb_abd=0.4,thumb_flex=0.3")
    parser.add_argument("--channel-bias", help="Optional per-channel additive bias after scaling, e.g. thumb_abd=-0.1")
    parser.add_argument("--max-step-delta", type=float, default=0.08, help="0 disables per-step target limiting.")
    parser.add_argument("--sample-every", type=int, default=5)
    parser.add_argument("--abort-current", type=float, default=4000.0)
    parser.add_argument("--abort-temp", type=float, default=65.0)
    parser.add_argument("--apply-rest-first", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--rest-after", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--rest-settle", type=float, default=0.4)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
