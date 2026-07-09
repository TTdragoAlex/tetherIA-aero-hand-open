#!/usr/bin/env python3
"""Profile Aero Hand servo current by movement and channel.

Use this when the goal is understanding why 100% gestures overload:
  - which servo/channel reaches the highest current
  - during which movement/hold it happens
  - whether the problem is isolated or spread across channels
  - how current compares across pose scales

Default mode is dry-run. Add --run when the hand is connected and clear.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, fmt  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402
from tetheria_run_sequence_safe import TETHERIA_TRAJECTORY, lerp, scaled_pose  # noqa: E402


LOG_DIR = REPO_ROOT / "logs"
OPEN_PALM = [0.0] * 7
CURRENT_MA_PER_RAW_UNIT = 6.5


@dataclass
class Sample:
    timestamp: str
    elapsed_s: float
    movement: str
    phase: str
    pose_scale: float
    command_pose: list[float]
    pos_norm: list[float]
    curr_ma: list[float]
    temp_c: list[float]

    @property
    def max_abs_current(self) -> float:
        return max(abs(value) for value in self.curr_ma)

    @property
    def max_abs_current_channel(self) -> int:
        return max(range(len(self.curr_ma)), key=lambda i: abs(self.curr_ma[i]))

    @property
    def max_temp(self) -> float:
        return max(self.temp_c)

    @property
    def curr_raw_units(self) -> list[float]:
        return [value / CURRENT_MA_PER_RAW_UNIT for value in self.curr_ma]


def timestamp_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def read_sample(
    hand: AeroHandController,
    started_at: float,
    movement: str,
    phase: str,
    pose_scale: float,
    command_pose: list[float],
) -> Sample:
    return Sample(
        timestamp=datetime.now().isoformat(timespec="milliseconds"),
        elapsed_s=time.monotonic() - started_at,
        movement=movement,
        phase=phase,
        pose_scale=pose_scale,
        command_pose=command_pose[:],
        pos_norm=hand.get_pos_norm(),
        curr_ma=hand.get_currents_ma(),
        temp_c=hand.get_temperatures_c(),
    )


def sample_to_row(sample: Sample) -> dict[str, float | str]:
    row: dict[str, float | str] = {
        "timestamp": sample.timestamp,
        "elapsed_s": sample.elapsed_s,
        "movement": sample.movement,
        "phase": sample.phase,
        "pose_scale": sample.pose_scale,
        "max_abs_current_ma": sample.max_abs_current,
        "max_abs_current_channel": sample.max_abs_current_channel,
        "max_abs_current_channel_name": CHANNEL_NAMES[sample.max_abs_current_channel],
        "max_temp_c": sample.max_temp,
    }
    for idx, name in enumerate(CHANNEL_NAMES):
        row[f"cmd_{idx}_{name}"] = sample.command_pose[idx]
        row[f"pos_{idx}_{name}"] = sample.pos_norm[idx]
        row[f"curr_ma_{idx}_{name}"] = sample.curr_ma[idx]
        row[f"curr_raw_{idx}_{name}"] = sample.curr_raw_units[idx]
        row[f"temp_c_{idx}_{name}"] = sample.temp_c[idx]
    return row


def csv_fieldnames() -> list[str]:
    fields = [
        "timestamp",
        "elapsed_s",
        "movement",
        "phase",
        "pose_scale",
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
            f"curr_raw_{idx}_{name}",
            f"temp_c_{idx}_{name}",
        ])
    return fields


def print_sample(sample: Sample, warn_current: float) -> None:
    ch = sample.max_abs_current_channel
    prefix = (
        f"[{sample.elapsed_s:7.2f}s] {sample.movement:20s} {sample.phase:8s} "
        f"max={sample.max_abs_current:7.1f}mA ch{ch}:{CHANNEL_NAMES[ch]} "
        f"temp={sample.max_temp:4.1f}C"
    )
    if sample.max_abs_current >= warn_current:
        prefix += "  WARN"
    print(prefix)


def enforce_abort(sample: Sample, abort_current: float, abort_temp: float) -> None:
    over_current = [i for i, value in enumerate(sample.curr_ma) if abs(value) >= abort_current]
    over_temp = [i for i, value in enumerate(sample.temp_c) if value >= abort_temp]
    if not over_current and not over_temp:
        return

    parts = []
    if over_current:
        parts.append("current " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={sample.curr_ma[i]:.1f}mA" for i in over_current))
    if over_temp:
        parts.append("temp " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={sample.temp_c[i]:.1f}C" for i in over_temp))
    raise RuntimeError("Safety abort: " + "; ".join(parts))


def update_stats(stats: dict, sample: Sample) -> None:
    movement = stats.setdefault("movements", {}).setdefault(
        sample.movement,
        {
            "max_abs_current_ma": 0.0,
            "max_abs_current_channel": None,
            "max_abs_current_channel_name": None,
            "max_temp_c": 0.0,
            "sample": None,
            "channel_max": [0.0] * 7,
        },
    )

    if sample.max_abs_current > movement["max_abs_current_ma"]:
        movement["max_abs_current_ma"] = sample.max_abs_current
        movement["max_abs_current_channel"] = sample.max_abs_current_channel
        movement["max_abs_current_channel_name"] = CHANNEL_NAMES[sample.max_abs_current_channel]
        movement["sample"] = sample
    movement["max_temp_c"] = max(movement["max_temp_c"], sample.max_temp)

    for idx, value in enumerate(sample.curr_ma):
        abs_value = abs(value)
        movement["channel_max"][idx] = max(movement["channel_max"][idx], abs_value)
        stats["channel_max"][idx] = max(stats["channel_max"][idx], abs_value)
        if abs_value >= stats["current_threshold"]:
            stats["channel_over_threshold_counts"][idx] += 1

    if sample.max_abs_current > stats["overall_max_abs_current_ma"]:
        stats["overall_max_abs_current_ma"] = sample.max_abs_current
        stats["overall_sample"] = sample
    stats["overall_max_temp_c"] = max(stats["overall_max_temp_c"], sample.max_temp)
    stats["sample_count"] += 1


def print_summary(stats: dict, target_current: float, csv_path: Path) -> None:
    print("\n=== Servo Current Profile Summary ===")
    print(f"samples: {stats['sample_count']}")
    print(f"csv: {csv_path}")
    print(f"max_temp_c: {stats['overall_max_temp_c']:.1f}")

    sample = stats["overall_sample"]
    if sample is not None:
        ch = sample.max_abs_current_channel
        print(
            "overall worst: "
            f"{sample.max_abs_current:.1f} mA on ch{ch}:{CHANNEL_NAMES[ch]} "
            f"during {sample.movement}/{sample.phase}"
        )
        print(f"  command_pose: {fmt(sample.command_pose, 1)}")
        print(f"  currents:     {fmt(sample.curr_ma, 1)}")
        print(f"  raw_units:    {fmt(sample.curr_raw_units, 1)}")
        print(f"  temps:        {fmt(sample.temp_c, 1)}")

    print("\nPer-channel max absolute current:")
    for idx, value in enumerate(stats["channel_max"]):
        count = stats["channel_over_threshold_counts"][idx]
        status = "OK"
        if value >= 2500:
            status = "HARD"
        elif value >= 1500:
            status = "HIGH"
        elif value >= 800:
            status = "LOADED"
        raw_value = value / CURRENT_MA_PER_RAW_UNIT
        print(
            f"  ch{idx}:{CHANNEL_NAMES[idx]:13s} max={value:7.1f}mA "
            f"raw={raw_value:6.1f} over_{target_current:.0f}mA_samples={count:3d} {status}"
        )

    print("\nWorst movements:")
    movements = sorted(
        stats["movements"].items(),
        key=lambda item: item[1]["max_abs_current_ma"],
        reverse=True,
    )
    for name, data in movements[:12]:
        ch = data["max_abs_current_channel"]
        channel_name = data["max_abs_current_channel_name"]
        print(
            f"  {name:20s} max={data['max_abs_current_ma']:7.1f}mA "
            f"ch{ch}:{channel_name} temp={data['max_temp_c']:.1f}C "
            f"channel_max={fmt(data['channel_max'], 1)}"
        )

    high_channels = [idx for idx, value in enumerate(stats["channel_max"]) if value >= target_current]
    if high_channels:
        named = ", ".join(f"ch{idx}:{CHANNEL_NAMES[idx]}" for idx in high_channels)
        print(f"\nChannels exceeding {target_current:.0f} mA: {named}")
    else:
        print(f"\nNo channels exceeded {target_current:.0f} mA.")


def profile_sequence(args: argparse.Namespace) -> int:
    if not args.run:
        print("Servo current profiler dry run. No serial connection or movement will happen.")
        print(f"pose_scale: {args.pose_scale:.2f}")
        print("Movements to profile:")
        for name, pose, duration in TETHERIA_TRAJECTORY:
            print(f"  {name:20s} pose={fmt(scaled_pose(pose, args.pose_scale), 1)} duration={duration:.2f}s")
        print("\nRun with --run after connecting the hand and clearing the workspace.")
        return 0

    csv_path = args.log or (LOG_DIR / f"servo_current_profile_{timestamp_for_filename()}.csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    stats = {
        "current_threshold": args.target_current,
        "sample_count": 0,
        "overall_max_abs_current_ma": 0.0,
        "overall_max_temp_c": 0.0,
        "overall_sample": None,
        "channel_max": [0.0] * 7,
        "channel_over_threshold_counts": [0] * 7,
        "movements": {},
    }

    trajectory = [(name, scaled_pose(pose, args.pose_scale), duration) for name, pose, duration in TETHERIA_TRAJECTORY]
    last_pose = trajectory[0][1][:]
    started_at = time.monotonic()

    with csv_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=csv_fieldnames())
        writer.writeheader()

        with AeroHandController(args.port, args.baud) as hand:
            try:
                hand.hand.set_joint_positions(OPEN_PALM)
                time.sleep(args.open_settle)
                initial = read_sample(hand, started_at, "initial_open", "settle", args.pose_scale, OPEN_PALM)
                writer.writerow(sample_to_row(initial))
                update_stats(stats, initial)
                print_sample(initial, args.warn_current)
                enforce_abort(initial, args.abort_current, args.abort_temp)

                for name, target_pose, duration in trajectory[1:]:
                    print(f"\nMovement {name}: {fmt(target_pose, 1)} over {duration:.2f}s")
                    steps = max(1, int(duration * args.rate))
                    sample_every = max(1, int(args.sample_period * args.rate))
                    for step in range(1, steps + 1):
                        pose = lerp(last_pose, target_pose, step / steps)
                        hand.hand.set_joint_positions(pose)
                        time.sleep(1.0 / args.rate)

                        if step == steps or step % sample_every == 0:
                            sample = read_sample(hand, started_at, name, "ramp", args.pose_scale, pose)
                            writer.writerow(sample_to_row(sample))
                            file.flush()
                            update_stats(stats, sample)
                            print_sample(sample, args.warn_current)
                            enforce_abort(sample, args.abort_current, args.abort_temp)

                    last_pose = target_pose[:]
                    hold_deadline = time.monotonic() + args.hold_sample_s
                    while time.monotonic() < hold_deadline:
                        time.sleep(args.sample_period)
                        sample = read_sample(hand, started_at, name, "hold", args.pose_scale, target_pose)
                        writer.writerow(sample_to_row(sample))
                        file.flush()
                        update_stats(stats, sample)
                        print_sample(sample, args.warn_current)
                        enforce_abort(sample, args.abort_current, args.abort_temp)

                hand.hand.set_joint_positions(OPEN_PALM)
                time.sleep(args.open_settle)
                final = read_sample(hand, started_at, "final_open", "settle", args.pose_scale, OPEN_PALM)
                writer.writerow(sample_to_row(final))
                update_stats(stats, final)
                print_sample(final, args.warn_current)
            except Exception:
                print("\n[recovery] sending open palm after exception/abort")
                hand.hand.set_joint_positions(OPEN_PALM)
                time.sleep(args.open_settle)
                try:
                    recovery = read_sample(hand, started_at, "recovered_open", "settle", args.pose_scale, OPEN_PALM)
                    writer.writerow(sample_to_row(recovery))
                    update_stats(stats, recovery)
                    print_sample(recovery, args.warn_current)
                finally:
                    print_summary(stats, args.target_current, csv_path)
                raise

    print_summary(stats, args.target_current, csv_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile Aero Hand servo currents by movement/channel.")
    parser.add_argument("--run", action="store_true", help="Actually move the hand. Omit for dry run.")
    parser.add_argument("--port", help="Serial port. Auto-detected if omitted.")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--pose-scale", type=float, default=1.0, help="Profile this command scale. Use 1.0 for full commands.")
    parser.add_argument("--rate", type=float, default=35.0, help="Command rate while interpolating gestures.")
    parser.add_argument("--sample-period", type=float, default=0.15, help="Telemetry sample period during ramps/holds.")
    parser.add_argument("--hold-sample-s", type=float, default=0.35, help="Seconds to keep sampling after each target is reached.")
    parser.add_argument("--open-settle", type=float, default=0.5, help="Seconds to wait after sending open palm.")
    parser.add_argument("--target-current", type=float, default=1500.0, help="Report channels/movements above this current.")
    parser.add_argument("--warn-current", type=float, default=800.0, help="Print WARN on samples above this current.")
    parser.add_argument("--abort-current", type=float, default=3500.0, help="Hard abort above this absolute current in mA.")
    parser.add_argument("--abort-temp", type=float, default=65.0, help="Hard abort above this temperature in C.")
    parser.add_argument("--log", type=Path, help="CSV output path. Defaults to logs/servo_current_profile_<timestamp>.csv")
    args = parser.parse_args()
    return profile_sequence(args)


if __name__ == "__main__":
    raise SystemExit(main())
