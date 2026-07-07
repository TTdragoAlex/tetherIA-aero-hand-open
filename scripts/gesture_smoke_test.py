#!/usr/bin/env python3
"""Conservative Aero Hand gesture smoke test.

Default mode is a dry run. Add --run to actually move the hand.
The script uses normal joint-space commands for gestures and logs current/temp
after every pose so we can catch unsafe loading early.
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

CHANNEL_NAMES = [
    "thumb_abd",
    "thumb_flex",
    "thumb_tendon",
    "index",
    "middle",
    "ring",
    "pinky",
]

# Compact 7-joint values in normalized GUI-style units, then converted to degrees.
# Keep the first pass gentle: these are not full grasps.
POSES = [
    ("open",              [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00], 1.0),
    ("index_small_curl",  [0.00, 0.00, 0.00, 0.18, 0.00, 0.00, 0.00], 1.0),
    ("open",              [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00], 0.8),
    ("four_finger_curl",  [0.00, 0.00, 0.00, 0.15, 0.15, 0.15, 0.15], 1.0),
    ("open",              [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00], 0.8),
    ("thumb_tiny_motion", [0.05, 0.03, 0.03, 0.00, 0.00, 0.00, 0.00], 1.0),
    ("open",              [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00], 1.0),
]


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def normalized_to_joint_degrees(hand: AeroHandController, values: list[float]) -> list[float]:
    lower = hand.hand.joint_lower_limits
    upper = hand.hand.joint_upper_limits
    return [lower[i] + (upper[i] - lower[i]) * clamp01(values[i]) for i in range(7)]


def lerp_pose(start: list[float], end: list[float], alpha: float) -> list[float]:
    return [start[i] + (end[i] - start[i]) * alpha for i in range(7)]


def telemetry(hand: AeroHandController, label: str, warn_current: float, warn_temp: float, abort_current: float, abort_temp: float) -> None:
    pos = hand.get_pos_norm()
    curr = hand.get_currents_ma()
    temp = hand.get_temperatures_c()
    current_warn = [i for i, value in enumerate(curr) if abs(value) >= warn_current]
    temp_warn = [i for i, value in enumerate(temp) if value >= warn_temp]
    print(f"[{label}] pos={fmt(pos)} curr={fmt(curr, 1)} temp={fmt(temp, 1)}")
    if current_warn:
        named = ", ".join(f"{i}:{CHANNEL_NAMES[i]}={curr[i]:.1f}mA" for i in current_warn)
        print(f"[{label}] WARN current: {named}")
    if temp_warn:
        named = ", ".join(f"{i}:{CHANNEL_NAMES[i]}={temp[i]:.1f}C" for i in temp_warn)
        print(f"[{label}] WARN temp: {named}")
    abort_curr = [i for i, value in enumerate(curr) if abs(value) >= abort_current]
    abort_temperature = [i for i, value in enumerate(temp) if value >= abort_temp]
    if abort_curr or abort_temperature:
        parts = []
        if abort_curr:
            parts.append("current " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={curr[i]:.1f}mA" for i in abort_curr))
        if abort_temperature:
            parts.append("temp " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={temp[i]:.1f}C" for i in abort_temperature))
        raise RuntimeError("Safety abort: " + "; ".join(parts))


def send_joint_pose(hand: AeroHandController, pose_norm: list[float], ramp_s: float, rate_hz: float) -> None:
    steps = max(1, int(ramp_s * rate_hz))
    # Use current actuator readings only for telemetry; joint target state starts from the last commanded pose.
    # The caller ramps by passing incremental poses, so this sends one pose per call.
    joint_degrees = normalized_to_joint_degrees(hand, pose_norm)
    hand.hand.set_joint_positions(joint_degrees)
    time.sleep(1.0 / rate_hz)


def run_sequence(args: argparse.Namespace) -> int:
    print("Gesture smoke test sequence:")
    for name, pose, hold in POSES:
        print(f"  {name:18s} pose={fmt(pose)} hold={hold:.1f}s")

    if not args.run:
        print("\nDry run only. Re-run with --run to move the hand.")
        return 0

    with AeroHandController(args.port, args.baud) as hand:
        telemetry(hand, "initial", args.warn_current, args.warn_temp, args.abort_current, args.abort_temp)
        last_pose = [0.0] * 7
        for name, target_pose, hold_s in POSES:
            print(f"\nMoving to {name}: {fmt(target_pose)}")
            steps = max(1, int(args.ramp * args.rate))
            for step in range(1, steps + 1):
                alpha = step / steps
                pose = lerp_pose(last_pose, target_pose, alpha)
                send_joint_pose(hand, pose, args.ramp / steps, args.rate)
            last_pose = target_pose[:]
            time.sleep(hold_s)
            telemetry(hand, name, args.warn_current, args.warn_temp, args.abort_current, args.abort_temp)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a conservative Aero Hand gesture smoke test.")
    parser.add_argument("--run", action="store_true", help="Actually move the hand. Omit for dry run.")
    parser.add_argument("--port", help="Serial port. Auto-detected if omitted.")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--rate", type=float, default=30.0, help="Command rate while ramping.")
    parser.add_argument("--ramp", type=float, default=1.0, help="Seconds to ramp between poses.")
    parser.add_argument("--warn-current", type=float, default=450.0, help="Warn above this absolute current in mA.")
    parser.add_argument("--warn-temp", type=float, default=55.0, help="Warn above this temperature in C.")
    parser.add_argument("--abort-current", type=float, default=2500.0, help="Abort above this absolute current in mA.")
    parser.add_argument("--abort-temp", type=float, default=60.0, help="Abort above this temperature in C.")
    args = parser.parse_args()
    return run_sequence(args)


if __name__ == "__main__":
    raise SystemExit(main())
