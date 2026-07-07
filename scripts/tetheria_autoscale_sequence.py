#!/usr/bin/env python3
"""Find a safer pose scale for TetherIA's official gesture sequence.

Default mode is a dry run. Add --run when the hand is connected and clear.

The runner tries the official sequence at progressively lower pose scales. A
scale is accepted only when the whole sequence completes below the target
current and temperature thresholds. Hard current/temperature thresholds abort
the current attempt immediately, send open palm, cool down, and retry lower.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, fmt  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402
from tetheria_run_sequence_safe import TETHERIA_TRAJECTORY, lerp, scaled_pose  # noqa: E402


OPEN_PALM = [0.0] * 7


@dataclass
class TelemetrySample:
    label: str
    pos: list[float]
    curr: list[float]
    temp: list[float]

    @property
    def max_abs_current(self) -> float:
        return max(abs(value) for value in self.curr)

    @property
    def max_temp(self) -> float:
        return max(self.temp)


class AttemptAbort(RuntimeError):
    pass


def read_telemetry(hand: AeroHandController, label: str) -> TelemetrySample:
    sample = TelemetrySample(
        label=label,
        pos=hand.get_pos_norm(),
        curr=hand.get_currents_ma(),
        temp=hand.get_temperatures_c(),
    )
    print(f"[{label}] pos={fmt(sample.pos)} curr={fmt(sample.curr, 1)} temp={fmt(sample.temp, 1)}")
    return sample


def warn_loaded_channels(sample: TelemetrySample, warn_current: float, warn_temp: float) -> None:
    current_warn = [i for i, value in enumerate(sample.curr) if abs(value) >= warn_current]
    temp_warn = [i for i, value in enumerate(sample.temp) if value >= warn_temp]
    if current_warn:
        named = ", ".join(f"{i}:{CHANNEL_NAMES[i]}={sample.curr[i]:.1f}mA" for i in current_warn)
        print(f"[{sample.label}] WARN current: {named}")
    if temp_warn:
        named = ", ".join(f"{i}:{CHANNEL_NAMES[i]}={sample.temp[i]:.1f}C" for i in temp_warn)
        print(f"[{sample.label}] WARN temp: {named}")


def enforce_hard_limits(sample: TelemetrySample, hard_current: float, abort_temp: float) -> None:
    over_current = [i for i, value in enumerate(sample.curr) if abs(value) >= hard_current]
    over_temp = [i for i, value in enumerate(sample.temp) if value >= abort_temp]
    if not over_current and not over_temp:
        return

    parts = []
    if over_current:
        parts.append("current " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={sample.curr[i]:.1f}mA" for i in over_current))
    if over_temp:
        parts.append("temp " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={sample.temp[i]:.1f}C" for i in over_temp))
    raise AttemptAbort("; ".join(parts))


def send_open(hand: AeroHandController, settle_s: float) -> None:
    hand.hand.set_joint_positions(OPEN_PALM)
    time.sleep(settle_s)


def run_scaled_attempt(hand: AeroHandController, args: argparse.Namespace, scale: float) -> tuple[float, float]:
    trajectory = [
        (name, scaled_pose(pose, scale), duration)
        for name, pose, duration in TETHERIA_TRAJECTORY
    ]
    max_current = 0.0
    max_temp = 0.0

    print(f"\n=== Attempt scale={scale:.2f} ===")
    initial = read_telemetry(hand, f"scale_{scale:.2f}_initial")
    warn_loaded_channels(initial, args.warn_current, args.warn_temp)
    enforce_hard_limits(initial, args.hard_current, args.abort_temp)
    max_current = max(max_current, initial.max_abs_current)
    max_temp = max(max_temp, initial.max_temp)

    last_pose = trajectory[0][1][:]
    hand.hand.set_joint_positions(last_pose)
    time.sleep(args.initial_settle)

    for name, target_pose, duration in trajectory[1:]:
        steps = max(1, int(duration * args.rate))
        print(f"Moving to {name}: {fmt(target_pose, 1)} over {duration:.2f}s")
        for step in range(1, steps + 1):
            pose = lerp(last_pose, target_pose, step / steps)
            hand.hand.set_joint_positions(pose)
            time.sleep(1.0 / args.rate)

        last_pose = target_pose[:]
        time.sleep(args.settle)
        sample = read_telemetry(hand, f"scale_{scale:.2f}_{name}")
        warn_loaded_channels(sample, args.warn_current, args.warn_temp)
        enforce_hard_limits(sample, args.hard_current, args.abort_temp)
        max_current = max(max_current, sample.max_abs_current)
        max_temp = max(max_temp, sample.max_temp)

    send_open(hand, args.open_settle)
    final = read_telemetry(hand, f"scale_{scale:.2f}_final_open")
    max_current = max(max_current, final.max_abs_current)
    max_temp = max(max_temp, final.max_temp)
    return max_current, max_temp


def scale_values(start: float, minimum: float, step: float) -> list[float]:
    values = []
    current = start
    while current >= minimum - 1e-9:
        values.append(round(current, 3))
        current -= step
    return values


def dry_run(args: argparse.Namespace) -> int:
    print("Autoscale dry run. No serial connection or movement will happen.")
    print("Candidate scales:", ", ".join(f"{value:.2f}" for value in scale_values(args.start_scale, args.min_scale, args.scale_step)))
    print(f"Accept if max current <= {args.target_current:.1f} mA and max temp <= {args.target_temp:.1f} C.")
    print(f"Hard abort if current >= {args.hard_current:.1f} mA or temp >= {args.abort_temp:.1f} C.")
    print("\nRun with --run after connecting the hand and clearing the workspace.")
    return 0


def run_autoscale(args: argparse.Namespace) -> int:
    if args.scale_step <= 0:
        raise ValueError("--scale-step must be positive")
    if args.min_scale > args.start_scale:
        raise ValueError("--min-scale must be <= --start-scale")

    best_scale = None
    with AeroHandController(args.port, args.baud) as hand:
        for scale in scale_values(args.start_scale, args.min_scale, args.scale_step):
            try:
                max_current, max_temp = run_scaled_attempt(hand, args, scale)
            except AttemptAbort as exc:
                print(f"[scale {scale:.2f}] HARD ABORT: {exc}")
                print("[recovery] sending open palm before retrying lower scale")
                send_open(hand, args.open_settle)
                read_telemetry(hand, f"scale_{scale:.2f}_recovered_open")
                if args.cooldown > 0:
                    print(f"[cooldown] waiting {args.cooldown:.1f}s")
                    time.sleep(args.cooldown)
                continue

            print(f"[scale {scale:.2f}] completed: max_current={max_current:.1f}mA max_temp={max_temp:.1f}C")
            if max_current <= args.target_current and max_temp <= args.target_temp:
                best_scale = scale
                print(f"\nACCEPTED scale={best_scale:.2f}")
                break
            print(
                f"[scale {scale:.2f}] too loaded for target "
                f"({max_current:.1f}mA / {max_temp:.1f}C), trying lower scale"
            )
            if args.cooldown > 0:
                print(f"[cooldown] waiting {args.cooldown:.1f}s")
                time.sleep(args.cooldown)

        send_open(hand, args.open_settle)

    if best_scale is None:
        print("\nNo scale met the target thresholds. Try a lower --min-scale or inspect mechanics.")
        return 2

    print(f"\nRecommended command:")
    print(f"  ./.venv/bin/python scripts/tetheria_run_sequence_safe.py --run --pose-scale {best_scale:.2f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-scale TetherIA's gesture sequence based on current/temp telemetry.")
    parser.add_argument("--run", action="store_true", help="Actually move the hand. Omit for dry run.")
    parser.add_argument("--port", help="Serial port. Auto-detected if omitted.")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--start-scale", type=float, default=1.0, help="First pose scale to try.")
    parser.add_argument("--min-scale", type=float, default=0.55, help="Lowest pose scale to try.")
    parser.add_argument("--scale-step", type=float, default=0.05, help="Scale decrement after failed attempts.")
    parser.add_argument("--target-current", type=float, default=1500.0, help="Accept only if max absolute current stays at/below this mA.")
    parser.add_argument("--target-temp", type=float, default=50.0, help="Accept only if max temperature stays at/below this C.")
    parser.add_argument("--hard-current", type=float, default=2500.0, help="Abort an attempt immediately above this absolute current mA.")
    parser.add_argument("--warn-current", type=float, default=450.0, help="Warn above this absolute current in mA.")
    parser.add_argument("--warn-temp", type=float, default=55.0, help="Warn above this temperature in C.")
    parser.add_argument("--abort-temp", type=float, default=60.0, help="Abort an attempt immediately above this temperature C.")
    parser.add_argument("--rate", type=float, default=50.0, help="Command rate while interpolating gestures.")
    parser.add_argument("--settle", type=float, default=0.15, help="Seconds to wait before telemetry after each gesture.")
    parser.add_argument("--initial-settle", type=float, default=0.5, help="Seconds to wait after the first open-palm command.")
    parser.add_argument("--open-settle", type=float, default=0.5, help="Seconds to wait after sending open palm.")
    parser.add_argument("--cooldown", type=float, default=10.0, help="Seconds to wait between failed attempts.")
    args = parser.parse_args()

    if not args.run:
        return dry_run(args)
    return run_autoscale(args)


if __name__ == "__main__":
    raise SystemExit(main())
