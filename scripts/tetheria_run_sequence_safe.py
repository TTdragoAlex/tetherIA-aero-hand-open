#!/usr/bin/env python3
"""Run TetherIA's official hand gesture sequence with telemetry safety checks.

The official example is saved at:
  upstream/tetheria-sdk-examples/run_sequence.py

This script keeps the same joint targets, but adds:
  - dry-run by default
  - current/temperature telemetry after each named gesture
  - abort thresholds before continuing to the next gesture
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, fmt  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES, telemetry  # noqa: E402


# Same compact 7-joint targets and timings as TetherIA's sdk/examples/run_sequence.py.
TETHERIA_TRAJECTORY = [
    ("open_palm", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 1.0),
    ("touch_pinkie", [100.0, 35.0, 23.0, 0.0, 0.0, 0.0, 50.0], 0.5),
    ("hold_pinkie", [100.0, 35.0, 23.0, 0.0, 0.0, 0.0, 50.0], 0.25),
    ("touch_ring", [100.0, 42.0, 23.0, 0.0, 0.0, 52.0, 0.0], 0.5),
    ("hold_ring", [100.0, 42.0, 23.0, 0.0, 0.0, 52.0, 0.0], 0.25),
    ("touch_middle", [83.0, 42.0, 23.0, 0.0, 50.0, 0.0, 0.0], 0.5),
    ("hold_middle", [83.0, 42.0, 23.0, 0.0, 50.0, 0.0, 0.0], 0.25),
    ("touch_index", [75.0, 25.0, 30.0, 50.0, 0.0, 0.0, 0.0], 0.5),
    ("hold_index", [75.0, 25.0, 30.0, 50.0, 0.0, 0.0, 0.0], 0.25),
    ("open_palm", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.5),
    ("hold_open", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.5),
    ("peace_setup_1", [90.0, 0.0, 0.0, 0.0, 0.0, 90.0, 90.0], 0.5),
    ("peace_setup_2", [90.0, 45.0, 60.0, 0.0, 0.0, 90.0, 90.0], 0.5),
    ("peace_hold", [90.0, 45.0, 60.0, 0.0, 0.0, 90.0, 90.0], 1.0),
    ("open_palm", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.5),
    ("hold_open", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.5),
    ("rockstar", [0.0, 0.0, 0.0, 0.0, 90.0, 90.0, 0.0], 0.5),
    ("rockstar_hold", [0.0, 0.0, 0.0, 0.0, 90.0, 90.0, 0.0], 1.0),
    ("open_palm", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.5),
]


def lerp(start: list[float], end: list[float], alpha: float) -> list[float]:
    return [start[i] + (end[i] - start[i]) * alpha for i in range(7)]


def scaled_pose(pose: list[float], scale: float) -> list[float]:
    return [value * scale for value in pose]


def print_sequence(scale: float) -> None:
    title = "TetherIA official run_sequence targets"
    if scale != 1.0:
        title += f" scaled to {scale:.0%}"
    print(title + ":")
    for name, pose, duration in TETHERIA_TRAJECTORY:
        print(f"  {name:15s} pose={fmt(scaled_pose(pose, scale), 1)} duration={duration:.2f}s")


def run_sequence(args: argparse.Namespace) -> int:
    print_sequence(args.pose_scale)
    print(f"\nCurrent channels: {', '.join(f'{i}:{name}' for i, name in enumerate(CHANNEL_NAMES))}")

    if not args.run:
        print("\nDry run only. Re-run with --run to move the hand.")
        return 0

    trajectory = [
        (name, scaled_pose(pose, args.pose_scale), duration)
        for name, pose, duration in TETHERIA_TRAJECTORY
    ]

    with AeroHandController(args.port, args.baud) as hand:
        telemetry(hand, "initial", args.warn_current, args.warn_temp, args.abort_current, args.abort_temp)
        last_pose = trajectory[0][1][:]
        hand.hand.set_joint_positions(last_pose)
        time.sleep(args.initial_settle)
        telemetry(hand, "after_initial_open", args.warn_current, args.warn_temp, args.abort_current, args.abort_temp)

        for name, target_pose, duration in trajectory[1:]:
            steps = max(1, int(duration * args.rate))
            print(f"\nMoving to {name}: {fmt(target_pose, 1)} over {duration:.2f}s")
            for step in range(1, steps + 1):
                pose = lerp(last_pose, target_pose, step / steps)
                hand.hand.set_joint_positions(pose)
                time.sleep(1.0 / args.rate)
            last_pose = target_pose[:]
            time.sleep(args.settle)
            telemetry(hand, name, args.warn_current, args.warn_temp, args.abort_current, args.abort_temp)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TetherIA's official gesture sequence with safety checks.")
    parser.add_argument("--run", action="store_true", help="Actually move the hand. Omit for dry run.")
    parser.add_argument("--port", help="Serial port. Auto-detected if omitted.")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--rate", type=float, default=50.0, help="Command rate while interpolating gestures.")
    parser.add_argument("--settle", type=float, default=0.15, help="Seconds to wait before telemetry after each gesture.")
    parser.add_argument("--initial-settle", type=float, default=0.5, help="Seconds to wait after the first open-palm command.")
    parser.add_argument("--pose-scale", type=float, default=0.85, help="Scale all official joint targets. 1.0 is exact TetherIA.")
    parser.add_argument("--warn-current", type=float, default=450.0, help="Warn above this absolute current in mA.")
    parser.add_argument("--warn-temp", type=float, default=55.0, help="Warn above this temperature in C.")
    parser.add_argument("--abort-current", type=float, default=2500.0, help="Abort above this absolute current in mA.")
    parser.add_argument("--abort-temp", type=float, default=65.0, help="Abort above this temperature in C.")
    args = parser.parse_args()
    return run_sequence(args)


if __name__ == "__main__":
    raise SystemExit(main())
