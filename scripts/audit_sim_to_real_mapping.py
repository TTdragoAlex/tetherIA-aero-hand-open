#!/usr/bin/env python3
"""Audit the sim-action to real-hand mapping without running a learned policy.

This script intentionally bypasses the actor network. It sends simple, isolated
raw actuator pulses and records GET_POS/GET_CURR so we can verify:

1. Physical SDK channel order: each named real channel moves when commanded.
2. Sim action mapping/sign: each sim action maps to the intended real channel
   and direction.

Use with the hand mounted, no cube, and fingers clear.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys
import time

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, DEFAULT_CALIBRATION_PATH, clamp01, fmt, load_raw_rest  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402
from live_policy_control import ACTION_SIGN_BY_PHYSICAL, SIM_ACTION_NAMES, SIM_TO_PHYSICAL_INDEX  # noqa: E402

LOG_DIR = REPO_ROOT / "logs"


def sim_to_physical_map() -> dict[int, int]:
    mapping = {}
    for physical_idx, sim_idx in enumerate(SIM_TO_PHYSICAL_INDEX):
        mapping[sim_idx] = physical_idx
    return mapping


def safety_check(curr: list[float], temp: list[float], abort_current: float, abort_temp: float) -> None:
    hot_curr = [i for i, value in enumerate(curr) if abs(value) >= abort_current]
    hot_temp = [i for i, value in enumerate(temp) if value >= abort_temp]
    parts = []
    if hot_curr:
        parts.append("current " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={curr[i]:.1f}mA" for i in hot_curr))
    if hot_temp:
        parts.append("temp " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={temp[i]:.1f}C" for i in hot_temp))
    if parts:
        raise RuntimeError("Safety abort: " + "; ".join(parts))


def move_smooth(hand: AeroHandController, start: list[float], target: list[float], steps: int, step_delay: float) -> None:
    for step in range(1, steps + 1):
        alpha = step / steps
        command = [(1.0 - alpha) * start[i] + alpha * target[i] for i in range(7)]
        hand.send_raw_actuators(command)
        time.sleep(step_delay)


def read_state(hand: AeroHandController) -> tuple[list[float], list[float], list[float]]:
    pos = hand.get_pos_norm()
    curr = hand.get_currents_ma()
    temp = hand.get_temperatures_c()
    return pos, curr, temp


def write_row(
    writer,
    phase: str,
    test_name: str,
    target: list[float],
    before,
    after,
    expected_channel: int,
    expected_delta_sign: float,
    min_delta: float,
) -> dict:
    before_pos, before_curr, before_temp = before
    after_pos, after_curr, after_temp = after
    deltas = [after_pos[i] - before_pos[i] for i in range(7)]
    dominant_channel = int(np.argmax(np.abs(deltas)))
    dominant_delta = deltas[dominant_channel]
    expected_delta = deltas[expected_channel]
    expected_sign_ok = np.sign(expected_delta) == np.sign(expected_delta_sign)
    expected_channel_ok = dominant_channel == expected_channel
    strong_enough = abs(expected_delta) >= min_delta
    passed = expected_channel_ok and expected_sign_ok and strong_enough
    row = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "phase": phase,
        "test": test_name,
        "max_abs_current_ma": max(abs(v) for v in after_curr),
        "max_temp_c": max(after_temp),
        "expected_channel": expected_channel,
        "expected_name": CHANNEL_NAMES[expected_channel],
        "expected_delta_sign": expected_delta_sign,
        "expected_delta": expected_delta,
        "dominant_delta_channel": dominant_channel,
        "dominant_delta_name": CHANNEL_NAMES[dominant_channel],
        "dominant_delta": dominant_delta,
        "pass": passed,
    }
    for idx, name in enumerate(CHANNEL_NAMES):
        row[f"target_{idx}_{name}"] = target[idx]
        row[f"before_pos_{idx}_{name}"] = before_pos[idx]
        row[f"after_pos_{idx}_{name}"] = after_pos[idx]
        row[f"delta_pos_{idx}_{name}"] = deltas[idx]
        row[f"after_curr_ma_{idx}_{name}"] = after_curr[idx]
        row[f"after_temp_c_{idx}_{name}"] = after_temp[idx]
    writer.writerow(row)
    return row


def fieldnames() -> list[str]:
    fields = [
        "timestamp",
        "phase",
        "test",
        "max_abs_current_ma",
        "max_temp_c",
        "expected_channel",
        "expected_name",
        "expected_delta_sign",
        "expected_delta",
        "dominant_delta_channel",
        "dominant_delta_name",
        "dominant_delta",
        "pass",
    ]
    for idx, name in enumerate(CHANNEL_NAMES):
        fields.extend(
            [
                f"target_{idx}_{name}",
                f"before_pos_{idx}_{name}",
                f"after_pos_{idx}_{name}",
                f"delta_pos_{idx}_{name}",
                f"after_curr_ma_{idx}_{name}",
                f"after_temp_c_{idx}_{name}",
            ]
        )
    return fields


def run(args: argparse.Namespace) -> int:
    raw_rest = load_raw_rest(args.calibration)
    sim_to_phys = sim_to_physical_map()
    log_path = args.log or LOG_DIR / f"mapping_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print("Sim-to-real mapping audit")
    print(f"run: {args.run}")
    print(f"raw_rest: {fmt(raw_rest)}")
    print(f"center: {args.center:.3f}; amplitude: {args.amplitude:.3f}; hold: {args.hold:.2f}s")
    print(f"min_delta for pass: {args.min_delta:.3f}")
    print(f"abort_current: {args.abort_current:.1f} mA; abort_temp: {args.abort_temp:.1f} C")
    print("Physical channel order:", CHANNEL_NAMES)
    print("Sim action order:", SIM_ACTION_NAMES)
    print("Current live mapping:")
    for sim_idx, sim_name in enumerate(SIM_ACTION_NAMES):
        physical_idx = sim_to_phys[sim_idx]
        sign = ACTION_SIGN_BY_PHYSICAL[physical_idx]
        print(f"  sim {sim_idx}:{sim_name:12s} -> physical {physical_idx}:{CHANNEL_NAMES[physical_idx]:13s} sign={sign:+.0f}")

    if not args.run:
        print("\nDry-run only. Add --run with the hand mounted and clear.")
        return 0

    with log_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames())
        writer.writeheader()
        results = []
        with AeroHandController(args.port, args.baud) as hand:
            try:
                current = hand.apply_rest(args.calibration, settle_s=args.rest_settle)
                rest_state = read_state(hand)
                safety_check(rest_state[1], rest_state[2], args.abort_current, args.abort_temp)

                if args.physical:
                    print("\nPhysical channel pulse audit")
                    for physical_idx, name in enumerate(CHANNEL_NAMES):
                        for direction in (1.0, -1.0):
                            baseline = list(raw_rest)
                            baseline[physical_idx] = clamp01(args.center)
                            target = list(baseline)
                            target[physical_idx] = clamp01(args.center + direction * args.amplitude)
                            if abs(target[physical_idx] - baseline[physical_idx]) < args.min_delta:
                                print(f"  skip physical {name:13s} dir={direction:+.0f}: clipped too close to baseline")
                                continue
                            move_smooth(hand, current, baseline, args.ramp_steps, args.step_delay)
                            time.sleep(args.rest_settle)
                            current = list(baseline)
                            before = read_state(hand)
                            move_smooth(hand, current, target, args.ramp_steps, args.step_delay)
                            time.sleep(args.hold)
                            after = read_state(hand)
                            safety_check(after[1], after[2], args.abort_current, args.abort_temp)
                            test_name = f"physical_{physical_idx}_{name}_{direction:+.0f}"
                            row = write_row(
                                writer,
                                "physical",
                                test_name,
                                target,
                                before,
                                after,
                                expected_channel=physical_idx,
                                expected_delta_sign=direction,
                                min_delta=args.min_delta,
                            )
                            results.append(row)
                            file.flush()
                            print(
                                f"  {'PASS' if row['pass'] else 'FAIL'} {test_name:28s} "
                                f"expected={row['expected_name']} {row['expected_delta']:+.3f} "
                                f"dominant={row['dominant_delta_name']} {row['dominant_delta']:+.3f} "
                                f"max_curr={row['max_abs_current_ma']:.1f}mA"
                            )
                            move_smooth(hand, target, raw_rest, args.ramp_steps, args.step_delay)
                            time.sleep(args.rest_settle)
                            current = list(raw_rest)

                print("\nSim action pulse audit")
                for sim_idx, sim_name in enumerate(SIM_ACTION_NAMES):
                    physical_idx = sim_to_phys[sim_idx]
                    physical_name = CHANNEL_NAMES[physical_idx]
                    sign = ACTION_SIGN_BY_PHYSICAL[physical_idx]
                    for action_value in (1.0, -1.0):
                        baseline = list(raw_rest)
                        baseline[physical_idx] = clamp01(args.center)
                        target = list(baseline)
                        expected_delta_sign = sign * action_value
                        target[physical_idx] = clamp01(args.center + expected_delta_sign * args.amplitude)
                        if abs(target[physical_idx] - baseline[physical_idx]) < args.min_delta:
                            print(f"  skip sim {sim_name:12s} action={action_value:+.0f}: clipped too close to baseline")
                            continue
                        move_smooth(hand, current, baseline, args.ramp_steps, args.step_delay)
                        time.sleep(args.rest_settle)
                        current = list(baseline)
                        before = read_state(hand)
                        move_smooth(hand, current, target, args.ramp_steps, args.step_delay)
                        time.sleep(args.hold)
                        after = read_state(hand)
                        safety_check(after[1], after[2], args.abort_current, args.abort_temp)
                        test_name = f"sim_{sim_idx}_{sim_name}_{action_value:+.0f}_to_{physical_name}"
                        row = write_row(
                            writer,
                            "sim_action",
                            test_name,
                            target,
                            before,
                            after,
                            expected_channel=physical_idx,
                            expected_delta_sign=expected_delta_sign,
                            min_delta=args.min_delta,
                        )
                        results.append(row)
                        file.flush()
                        print(
                            f"  {'PASS' if row['pass'] else 'FAIL'} {test_name:38s} "
                            f"expected={row['expected_name']} {row['expected_delta']:+.3f} "
                            f"dominant={row['dominant_delta_name']} {row['dominant_delta']:+.3f} "
                            f"max_curr={row['max_abs_current_ma']:.1f}mA"
                        )
                        move_smooth(hand, target, raw_rest, args.ramp_steps, args.step_delay)
                        time.sleep(args.rest_settle)
                        current = list(raw_rest)
            finally:
                print("\n[recovery] sending raw rest")
                hand.apply_rest(args.calibration, settle_s=args.rest_settle)

    failures = [row for row in results if not row["pass"]]
    print("\nSummary")
    print(f"  tests: {len(results)}")
    print(f"  passed: {len(results) - len(failures)}")
    print(f"  failed: {len(failures)}")
    for row in failures:
        print(
            f"  FAIL {row['phase']} {row['test']}: "
            f"expected {row['expected_name']} {row['expected_delta']:+.3f}, "
            f"dominant {row['dominant_delta_name']} {row['dominant_delta']:+.3f}"
        )

    print(f"\nAudit complete. Log: {log_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Aero sim-to-real action/channel mapping.")
    parser.add_argument("--run", action="store_true", help="Actually move the hand. Omit for dry-run.")
    parser.add_argument("--physical", action="store_true", help="Also pulse each physical channel directly before sim-action pulses.")
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION_PATH)
    parser.add_argument("--center", type=float, default=0.35, help="Per-channel baseline used to test both directions away from rest.")
    parser.add_argument("--amplitude", type=float, default=0.14)
    parser.add_argument("--min-delta", type=float, default=0.035)
    parser.add_argument("--hold", type=float, default=0.35)
    parser.add_argument("--ramp-steps", type=int, default=8)
    parser.add_argument("--step-delay", type=float, default=0.035)
    parser.add_argument("--rest-settle", type=float, default=0.35)
    parser.add_argument("--abort-current", type=float, default=2500.0)
    parser.add_argument("--abort-temp", type=float, default=60.0)
    parser.add_argument("--log", type=Path)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
