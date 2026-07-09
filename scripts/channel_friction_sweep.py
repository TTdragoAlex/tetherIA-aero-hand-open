#!/usr/bin/env python3
"""Sweep Aero Hand channels one at a time to find no-cube high-current zones."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, DEFAULT_CALIBRATION_PATH, fmt, load_raw_rest  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402
from replay_policy_trace_safe import channel_index, parse_channel_values  # noqa: E402


LOG_DIR = REPO_ROOT / "logs"
CHANNEL_PRESETS = {
    "fingers": ["index", "middle", "ring", "pinky"],
    "four_fingers": ["index", "middle", "ring", "pinky"],
    "no_thumb": ["index", "middle", "ring", "pinky"],
}


def timestamp_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def make_fieldnames() -> list[str]:
    fields = [
        "timestamp",
        "elapsed_s",
        "channel",
        "channel_name",
        "phase",
        "target_value",
        "event",
        "max_abs_current_ma",
        "max_abs_current_channel",
        "max_abs_current_channel_name",
        "max_temp_c",
    ]
    for idx, name in enumerate(CHANNEL_NAMES):
        fields.extend([
            f"cmd_{idx}_{name}",
            f"pos_{idx}_{name}",
            f"curr_ma_{idx}_{name}",
            f"temp_c_{idx}_{name}",
        ])
    return fields


def row_from_sample(
    started: float,
    channel: int,
    phase: str,
    event: str,
    command: list[float],
    pos: list[float],
    curr: list[float],
    temp: list[float],
) -> dict[str, float | str | int]:
    max_ch = max(range(len(curr)), key=lambda idx: abs(curr[idx]))
    row: dict[str, float | str | int] = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "elapsed_s": time.monotonic() - started,
        "channel": channel,
        "channel_name": CHANNEL_NAMES[channel],
        "phase": phase,
        "target_value": command[channel],
        "event": event,
        "max_abs_current_ma": abs(curr[max_ch]),
        "max_abs_current_channel": max_ch,
        "max_abs_current_channel_name": CHANNEL_NAMES[max_ch],
        "max_temp_c": max(temp),
    }
    for idx, name in enumerate(CHANNEL_NAMES):
        row[f"cmd_{idx}_{name}"] = command[idx]
        row[f"pos_{idx}_{name}"] = pos[idx]
        row[f"curr_ma_{idx}_{name}"] = curr[idx]
        row[f"temp_c_{idx}_{name}"] = temp[idx]
    return row


def over_current_channels(curr: list[float], current_limit: float) -> list[int]:
    return [idx for idx, value in enumerate(curr) if abs(value) >= current_limit]


def enforce_emergency(curr: list[float], temp: list[float], emergency_current: float, abort_temp: float) -> None:
    over_current = over_current_channels(curr, emergency_current)
    over_temp = [idx for idx, value in enumerate(temp) if value >= abort_temp]
    if not over_current and not over_temp:
        return
    parts = []
    if over_current:
        parts.append("current " + ", ".join(f"{idx}:{CHANNEL_NAMES[idx]}={curr[idx]:.1f}mA" for idx in over_current))
    if over_temp:
        parts.append("temp " + ", ".join(f"{idx}:{CHANNEL_NAMES[idx]}={temp[idx]:.1f}C" for idx in over_temp))
    raise RuntimeError("Emergency abort: " + "; ".join(parts))


def print_row(row: dict[str, float | str | int], warn_current: float) -> None:
    status = " WARN" if float(row["max_abs_current_ma"]) >= warn_current else ""
    print(
        f"[{row['elapsed_s']:7.2f}s] ch{row['channel']}:{row['channel_name']:13s} "
        f"{row['phase']:10s} target={row['target_value']:.3f} "
        f"max={row['max_abs_current_ma']:7.1f}mA "
        f"max_ch={row['max_abs_current_channel_name']} "
        f"temp={row['max_temp_c']:.1f}C{status}"
    )


def target_values(start: float, stop: float, step: float) -> list[float]:
    values = []
    current = start
    while current <= stop + 1e-9:
        values.append(round(current, 6))
        current += step
    return values


def parse_channels(spec: str) -> list[int]:
    channels: list[int] = []
    for item in spec.split(","):
        label = item.strip()
        if not label:
            continue
        preset = CHANNEL_PRESETS.get(label.lower())
        if preset:
            channels.extend(channel_index(name) for name in preset)
        else:
            channels.append(channel_index(label))
    return channels


def main() -> int:
    parser = argparse.ArgumentParser(description="No-cube one-channel friction/current sweep.")
    parser.add_argument("--run", action="store_true", help="Actually move the physical hand. Omit for dry run.")
    parser.add_argument(
        "--channels",
        default="middle",
        help=(
            "Comma-separated channels by name/index, e.g. middle,index,thumb_flex. "
            "Presets: fingers/four_fingers/no_thumb = index,middle,ring,pinky."
        ),
    )
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--stop", type=float, default=0.55)
    parser.add_argument("--step", type=float, default=0.05)
    parser.add_argument("--hold", type=float, default=0.35, help="Hold/sample seconds at each target.")
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--max-step-delta", type=float, default=0.02, help="Max command change per tick while ramping.")
    parser.add_argument("--baseline", help="Optional comma-separated baseline pose for non-swept channels.")
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION_PATH)
    parser.add_argument(
        "--skip-current",
        type=float,
        default=2500.0,
        help="If the swept channel reaches this current, log it, return to rest, and continue with the next channel.",
    )
    parser.add_argument(
        "--emergency-current",
        type=float,
        default=3500.0,
        help="Hard whole-program abort above this absolute current in any channel.",
    )
    parser.add_argument("--abort-temp", type=float, default=65.0)
    parser.add_argument("--warn-current", type=float, default=1000.0)
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()

    channels = parse_channels(args.channels)
    values = target_values(args.start, args.stop, args.step)
    baseline_values = parse_channel_values(args.baseline) if args.baseline else [None] * len(CHANNEL_NAMES)
    rest = load_raw_rest(args.calibration)
    baseline = [
        float(baseline_values[idx]) if baseline_values[idx] is not None else rest[idx]
        for idx in range(len(CHANNEL_NAMES))
    ]

    print("No-cube channel friction sweep")
    print(f"channels: {', '.join(CHANNEL_NAMES[idx] for idx in channels)}")
    print(f"values: {values}")
    print(f"baseline: {fmt(baseline)}")
    print(f"max_step_delta: {args.max_step_delta:.3f}")
    print(f"skip_current: {args.skip_current:.1f} mA")
    print(f"emergency_current: {args.emergency_current:.1f} mA")

    if not args.run:
        print("\nDry run only. Add --run when the hand is connected, clear, and cube removed.")
        return 0

    log_path = args.log or LOG_DIR / f"channel_friction_sweep_{timestamp_for_filename()}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    dt = 1.0 / args.rate

    with log_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=make_fieldnames())
        writer.writeheader()
        with AeroHandController(args.port, args.baud) as hand:
            current_command = rest[:]
            try:
                hand.apply_rest(args.calibration, settle_s=0.5)
                for channel in channels:
                    skip_channel = False
                    for value in values:
                        if skip_channel:
                            break
                        target = baseline[:]
                        target[channel] = value
                        while True:
                            done = True
                            for idx in range(len(current_command)):
                                delta = target[idx] - current_command[idx]
                                if abs(delta) > args.max_step_delta:
                                    current_command[idx] += args.max_step_delta if delta > 0 else -args.max_step_delta
                                    done = False
                                else:
                                    current_command[idx] = target[idx]
                            hand.send_raw_actuators(current_command)
                            time.sleep(dt)
                            if done:
                                break

                        time.sleep(args.hold)
                        pos = hand.get_pos_norm()
                        curr = hand.get_currents_ma()
                        temp = hand.get_temperatures_c()
                        event = "ok"
                        swept_current = abs(curr[channel])
                        if swept_current >= args.skip_current:
                            event = "skip_channel"
                        row = row_from_sample(started, channel, "hold", event, current_command, pos, curr, temp)
                        writer.writerow(row)
                        file.flush()
                        print_row(row, args.warn_current)
                        enforce_emergency(curr, temp, args.emergency_current, args.abort_temp)
                        if event == "skip_channel":
                            print(
                                f"[skip] ch{channel}:{CHANNEL_NAMES[channel]} reached "
                                f"{swept_current:.1f}mA at target={value:.3f}; returning to rest and continuing."
                            )
                            skip_channel = True

                    target = rest[:]
                    while any(abs(current_command[idx] - target[idx]) > 1e-9 for idx in range(len(current_command))):
                        for idx in range(len(current_command)):
                            delta = target[idx] - current_command[idx]
                            if abs(delta) > args.max_step_delta:
                                current_command[idx] += args.max_step_delta if delta > 0 else -args.max_step_delta
                            else:
                                current_command[idx] = target[idx]
                        hand.send_raw_actuators(current_command)
                        time.sleep(dt)
                    time.sleep(0.35)
                    if skip_channel:
                        pos = hand.get_pos_norm()
                        curr = hand.get_currents_ma()
                        temp = hand.get_temperatures_c()
                        row = row_from_sample(started, channel, "recovered", "after_skip", current_command, pos, curr, temp)
                        writer.writerow(row)
                        file.flush()
                        print_row(row, args.warn_current)
                        enforce_emergency(curr, temp, args.emergency_current, args.abort_temp)

            except Exception:
                print("\n[recovery] sending raw rest after exception/abort")
                hand.apply_rest(args.calibration, settle_s=0.5)
                raise

    print(f"\nSweep complete. Log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
