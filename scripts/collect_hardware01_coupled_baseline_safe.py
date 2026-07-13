#!/usr/bin/env python3
"""Collect no-object current samples at sparse, known hardware01 trace poses.

This is a calibration collector, not a policy runner. It reuses the current
best real-hand-fitted trace, moves to sparse checkpoints one at a time, and
returns to raw rest after each checkpoint. A low soft limit skips a pose before
the normal hard abort limit is approached.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys
import time
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, DEFAULT_CALIBRATION_PATH, fmt, load_raw_rest  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402
from replay_hardware01_u_trace_safe import PRESETS, cap_step, load_trace, parse_channel_values, scale_target  # noqa: E402


LOG_DIR = REPO_ROOT / "logs"
DEFAULT_PRESET = "physics_id_rollout0_real_hand_fitted"


def max_channel(values: list[float]) -> tuple[int, float]:
    idx = max(range(len(values)), key=lambda item: abs(values[item]))
    return idx, abs(values[idx])


def current_or_temp_limit(curr: list[float], temp: list[float], current_limit: float, temp_limit: float) -> str | None:
    current_idx, current_max = max_channel(curr)
    temp_idx = max(range(len(temp)), key=temp.__getitem__)
    if current_max >= current_limit:
        return f"current {current_idx}:{CHANNEL_NAMES[current_idx]}={curr[current_idx]:.1f}mA"
    if temp[temp_idx] >= temp_limit:
        return f"temp {temp_idx}:{CHANNEL_NAMES[temp_idx]}={temp[temp_idx]:.1f}C"
    return None


def make_fieldnames() -> list[str]:
    fields = ["timestamp", "elapsed_s", "pose_index", "source_step", "event", "note"]
    for idx, name in enumerate(CHANNEL_NAMES):
        fields.extend([
            f"target_{idx}_{name}",
            f"pos_{idx}_{name}",
            f"curr_ma_{idx}_{name}",
            f"temp_c_{idx}_{name}",
        ])
    return fields


def write_row(
    writer: csv.DictWriter,
    started: float,
    pose_index: int,
    source_step: int,
    event: str,
    note: str,
    target: list[float],
    pos: list[float],
    curr: list[float],
    temp: list[float],
) -> None:
    row: dict[str, float | int | str] = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "elapsed_s": time.monotonic() - started,
        "pose_index": pose_index,
        "source_step": source_step,
        "event": event,
        "note": note,
    }
    for idx, name in enumerate(CHANNEL_NAMES):
        row[f"target_{idx}_{name}"] = target[idx]
        row[f"pos_{idx}_{name}"] = pos[idx]
        row[f"curr_ma_{idx}_{name}"] = curr[idx]
        row[f"temp_c_{idx}_{name}"] = temp[idx]
    writer.writerow(row)


def selected_trace_poses(args: argparse.Namespace) -> list[dict[str, object]]:
    preset = PRESETS[args.preset]
    trace_path = Path(args.trace) if args.trace else Path(preset["trace"])
    playback_scale = args.playback_scale if args.playback_scale is not None else float(preset["playback_scale"])
    scale_center = args.scale_center
    channel_scale = parse_channel_values(args.channel_scale or str(preset["channel_scale"]), default=1.0)
    channel_bias = parse_channel_values(args.channel_bias or str(preset["channel_bias"]), default=0.0)
    rows = load_trace(trace_path)
    selected = []
    for row_idx in range(0, len(rows), args.stride):
        row = rows[row_idx]
        target = scale_target(row["target"], playback_scale, scale_center, channel_scale, channel_bias)
        selected.append({"source_step": int(row["step"]), "target": target})
    if selected[-1]["source_step"] != int(rows[-1]["step"]):
        row = rows[-1]
        selected.append(
            {
                "source_step": int(row["step"]),
                "target": scale_target(row["target"], playback_scale, scale_center, channel_scale, channel_bias),
            }
        )
    if args.start_pose_index < 0:
        raise ValueError("--start-pose-index must be >= 0")
    if args.start_pose_index >= len(selected):
        raise ValueError(f"--start-pose-index must be below {len(selected)}")
    selected = selected[args.start_pose_index:]
    if args.max_poses is not None:
        if args.max_poses < 1:
            raise ValueError("--max-poses must be >= 1")
        selected = selected[:args.max_poses]
    return selected


def read_telemetry(hand: AeroHandController) -> tuple[list[float], list[float], list[float]]:
    return hand.get_pos_norm(), hand.get_currents_ma(), hand.get_temperatures_c()


def ramp_to(
    hand: AeroHandController,
    start: list[float],
    target: list[float],
    args: argparse.Namespace,
    *,
    enforce_soft_limit: bool,
    on_step: Callable[[list[float], list[float], list[float], list[float], str | None], None] | None = None,
) -> tuple[list[float], list[float], list[float], list[float], str | None]:
    """Move in small raw-command steps and sample telemetry after every step."""
    current_target = list(start)
    while True:
        current_target = cap_step(current_target, target, args.max_step_delta)
        hand.send_raw_actuators(current_target)
        time.sleep(1.0 / args.rate)
        pos, curr, temp = read_telemetry(hand)
        hard = current_or_temp_limit(curr, temp, args.abort_current, args.abort_temp)
        soft = current_or_temp_limit(curr, temp, args.soft_current, args.soft_temp) if enforce_soft_limit else None
        note = f"hard_abort: {hard}" if hard else (f"soft_skip: {soft}" if soft else None)
        if on_step is not None:
            on_step(current_target, pos, curr, temp, note)
        if hard:
            return current_target, pos, curr, temp, note
        if soft:
            return current_target, pos, curr, temp, note
        if all(abs(current_target[idx] - target[idx]) < 1e-6 for idx in range(7)):
            return current_target, pos, curr, temp, None


def run(args: argparse.Namespace) -> int:
    if args.stride < 1:
        raise ValueError("--stride must be >= 1")
    if not 0.0 < args.max_step_delta <= 0.08:
        raise ValueError("--max-step-delta must be in (0, 0.08]")
    if not 0.0 < args.soft_current < args.abort_current:
        raise ValueError("--soft-current must be positive and below --abort-current")

    poses = selected_trace_poses(args)
    print("Coupled no-object current collector")
    print(f"preset: {args.preset}; sparse poses: {len(poses)}; source stride: {args.stride}")
    print(f"soft_current: {args.soft_current:.0f}mA; hard_current: {args.abort_current:.0f}mA")
    print(f"soft_temp: {args.soft_temp:.1f}C; hard_temp: {args.abort_temp:.1f}C")
    print(f"max_step_delta: {args.max_step_delta:.3f}; rate: {args.rate:.1f}Hz")
    for pose_index, pose in enumerate(poses):
        print(f"  pose {pose_index:02d} source_step={pose['source_step']:>3} target={fmt(pose['target'])}")

    if not args.run:
        print("\nDry run only. This collector will not move the hand without --run.")
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = args.log or LOG_DIR / f"coupled_current_baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    rest = load_raw_rest(args.calibration)
    started = time.monotonic()
    with log_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=make_fieldnames(), lineterminator="\n")
        writer.writeheader()
        with AeroHandController(args.port, args.baud) as hand:
            current_target = hand.apply_rest(args.calibration, settle_s=args.rest_settle)
            try:
                pos, curr, temp = read_telemetry(hand)
                hard = current_or_temp_limit(curr, temp, args.abort_current, args.abort_temp)
                write_row(writer, started, -1, -1, "rest", hard or "", current_target, pos, curr, temp)
                file.flush()
                if hard:
                    raise RuntimeError(f"Initial rest is over the hard limit: {hard}")

                for pose_index, pose in enumerate(poses):
                    target = list(pose["target"])
                    source_step = int(pose["source_step"])

                    def log_move_step(step_target, step_pos, step_curr, step_temp, step_note):
                        write_row(
                            writer,
                            started,
                            pose_index,
                            source_step,
                            "move_ramp" if step_note is None else step_note.split(":", 1)[0],
                            step_note or "",
                            step_target,
                            step_pos,
                            step_curr,
                            step_temp,
                        )

                    current_target, pos, curr, temp, note = ramp_to(
                        hand, current_target, target, args, enforce_soft_limit=True, on_step=log_move_step
                    )
                    if note is None:
                        time.sleep(args.settle)
                        for hold_index in range(args.hold_samples):
                            if hold_index:
                                time.sleep(args.hold_interval)
                            pos, curr, temp = read_telemetry(hand)
                            hard = current_or_temp_limit(curr, temp, args.abort_current, args.abort_temp)
                            soft = current_or_temp_limit(curr, temp, args.soft_current, args.soft_temp)
                            if hard:
                                note = f"hard_abort: {hard}"
                            elif soft:
                                note = f"soft_skip: {soft}"
                            else:
                                note = None
                            event = "sample" if hold_index == args.hold_samples - 1 and note is None else "hold_sample"
                            if note:
                                event = note.split(":", 1)[0]
                            write_row(
                                writer,
                                started,
                                pose_index,
                                source_step,
                                event,
                                note or f"hold={hold_index + 1}/{args.hold_samples}",
                                current_target,
                                pos,
                                curr,
                                temp,
                            )
                            file.flush()
                            if note:
                                break
                    event = "sample" if not note else note.split(":", 1)[0]
                    print(f"[{pose_index:02d}] {event:10s} target={fmt(current_target)} max_current={max(abs(v) for v in curr):.1f}mA")

                    # Return to rest after every pose. A soft limit does not block
                    # opening, but a hard limit still aborts immediately.

                    def log_return_step(step_target, step_pos, step_curr, step_temp, step_note):
                        write_row(
                            writer,
                            started,
                            pose_index,
                            source_step,
                            "return_ramp" if step_note is None else step_note.split(":", 1)[0],
                            step_note or "",
                            step_target,
                            step_pos,
                            step_curr,
                            step_temp,
                        )

                    current_target, rest_pos, rest_curr, rest_temp, rest_note = ramp_to(
                        hand, current_target, rest, args, enforce_soft_limit=False, on_step=log_return_step
                    )
                    write_row(
                        writer,
                        started,
                        pose_index,
                        source_step,
                        "return_rest" if rest_note is None else rest_note.split(":", 1)[0],
                        rest_note or "",
                        current_target,
                        rest_pos,
                        rest_curr,
                        rest_temp,
                    )
                    file.flush()
                    if note and note.startswith("hard_abort"):
                        raise RuntimeError(note)
                    if rest_note:
                        raise RuntimeError(rest_note)
            finally:
                hand.apply_rest(args.calibration, settle_s=args.rest_settle)
    print(f"\nCollector complete. Log: {log_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect safe no-object coupled-position/current samples from a fitted trace.")
    parser.add_argument("--run", action="store_true", help="Actually move the hand. Omit for dry-run preview.")
    parser.add_argument("--preset", choices=tuple(PRESETS), default=DEFAULT_PRESET)
    parser.add_argument("--trace", type=Path, help="Override the preset trace; transform still defaults to the preset values.")
    parser.add_argument("--stride", type=int, default=12, help="Use every Nth trace point plus the final point.")
    parser.add_argument("--start-pose-index", type=int, default=0, help="Zero-based index in the sparse pose list to begin collecting.")
    parser.add_argument("--max-poses", type=int, help="Number of sparse poses to collect after --start-pose-index.")
    parser.add_argument("--playback-scale", type=float)
    parser.add_argument("--scale-center", type=float, default=0.5)
    parser.add_argument("--channel-scale", default="")
    parser.add_argument("--channel-bias", default="")
    parser.add_argument("--max-step-delta", type=float, default=0.015)
    parser.add_argument("--rate", type=float, default=10.0)
    parser.add_argument("--settle", type=float, default=0.6)
    parser.add_argument("--hold-samples", type=int, default=8, help="Settled telemetry samples per completed pose.")
    parser.add_argument("--hold-interval", type=float, default=0.10, help="Seconds between settled telemetry samples.")
    parser.add_argument("--rest-settle", type=float, default=0.6)
    parser.add_argument("--soft-current", type=float, default=1800.0)
    parser.add_argument("--abort-current", type=float, default=3000.0)
    parser.add_argument("--soft-temp", type=float, default=55.0)
    parser.add_argument("--abort-temp", type=float, default=60.0)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION_PATH)
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    if args.hold_samples < 1:
        raise ValueError("--hold-samples must be >= 1")
    if args.hold_interval < 0.0:
        raise ValueError("--hold-interval must be >= 0")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
