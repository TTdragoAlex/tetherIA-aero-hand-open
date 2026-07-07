#!/usr/bin/env python3
"""Interactively tune and save the Aero Hand raw open/rest actuator pose."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import shutil
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, DEFAULT_CALIBRATION_PATH, clamp01, fmt, load_raw_rest  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402
from replay_policy_trace_safe import channel_index  # noqa: E402


def print_help() -> None:
    print(
        """
Commands:
  show                         print current target
  send                         send current target and read current/temp
  pos                          read GET_POS/GET_CURR/GET_TEMP without changing target
  loadpos                      set target to current GET_POS, then send it
  set <channel> <value>         set raw target, example: set ring 0.03
  add <channel> <delta>         nudge raw target, example: add thumb_flex -0.005
  save                         save current target to aero_hand_calibration.json
  rest                         reload saved rest and send it
  help                         show this help
  quit                         exit after sending saved rest

Channels:
"""
    )
    for idx, name in enumerate(CHANNEL_NAMES):
        print(f"  {idx}: {name}")


def telemetry(hand: AeroHandController, warn_current: float, abort_current: float, abort_temp: float) -> None:
    pos = hand.get_pos_norm()
    curr = hand.get_currents_ma()
    temp = hand.get_temperatures_c()
    print("  pos :", fmt(pos))
    print("  curr:", fmt(curr, 1))
    print("  temp:", fmt(temp, 1))
    warn = [idx for idx, value in enumerate(curr) if abs(value) >= warn_current]
    abort = [idx for idx, value in enumerate(curr) if abs(value) >= abort_current]
    hot = [idx for idx, value in enumerate(temp) if value >= abort_temp]
    if warn:
        print("  WARN current:", ", ".join(f"{CHANNEL_NAMES[i]}={curr[i]:.1f}mA" for i in warn))
    if abort or hot:
        parts = []
        if abort:
            parts.append("current " + ", ".join(f"{CHANNEL_NAMES[i]}={curr[i]:.1f}mA" for i in abort))
        if hot:
            parts.append("temp " + ", ".join(f"{CHANNEL_NAMES[i]}={temp[i]:.1f}C" for i in hot))
        raise RuntimeError("Safety abort: " + "; ".join(parts))


def ramp_send(hand: AeroHandController, current: list[float], target: list[float], max_step_delta: float, rate: float) -> list[float]:
    dt = 1.0 / rate
    command = current[:]
    while True:
        done = True
        for idx in range(len(command)):
            delta = target[idx] - command[idx]
            if abs(delta) > max_step_delta:
                command[idx] += max_step_delta if delta > 0 else -max_step_delta
                done = False
            else:
                command[idx] = target[idx]
        hand.send_raw_actuators(command)
        time.sleep(dt)
        if done:
            return command


def save_calibration(path: Path, target: list[float]) -> None:
    if path.exists():
        backup = path.with_suffix(path.suffix + f".bak-{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(path, backup)
        print(f"  backup: {backup}")
    data = {
        "raw_actuator_rest": [clamp01(value) for value in target],
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": "Raw normalized actuator rest pose saved from manual_raw_rest_calibration.py.",
    }
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  saved: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manually tune raw open/rest actuator calibration.")
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION_PATH)
    parser.add_argument("--max-step-delta", type=float, default=0.005)
    parser.add_argument("--rate", type=float, default=30.0)
    parser.add_argument("--warn-current", type=float, default=1000.0)
    parser.add_argument("--abort-current", type=float, default=2500.0)
    parser.add_argument("--abort-temp", type=float, default=58.0)
    args = parser.parse_args()

    target = load_raw_rest(args.calibration)
    current_command = target[:]
    print("Manual raw rest calibration")
    print("Starting target:", fmt(target))
    print_help()

    with AeroHandController(args.port, args.baud) as hand:
        try:
            current_command = ramp_send(hand, current_command, target, args.max_step_delta, args.rate)
            telemetry(hand, args.warn_current, args.abort_current, args.abort_temp)
            while True:
                raw = input("\ncal> ").strip()
                if not raw:
                    continue
                parts = raw.split()
                cmd = parts[0].lower()
                if cmd in {"quit", "exit", "q"}:
                    saved = load_raw_rest(args.calibration)
                    print("Returning to saved rest:", fmt(saved))
                    ramp_send(hand, current_command, saved, args.max_step_delta, args.rate)
                    return 0
                if cmd == "help":
                    print_help()
                    continue
                if cmd == "show":
                    print("target:", fmt(target))
                    continue
                if cmd == "pos":
                    telemetry(hand, args.warn_current, args.abort_current, args.abort_temp)
                    continue
                if cmd == "send":
                    current_command = ramp_send(hand, current_command, target, args.max_step_delta, args.rate)
                    telemetry(hand, args.warn_current, args.abort_current, args.abort_temp)
                    continue
                if cmd == "loadpos":
                    target = hand.get_pos_norm()
                    print("target loaded from GET_POS:", fmt(target))
                    current_command = ramp_send(hand, current_command, target, args.max_step_delta, args.rate)
                    telemetry(hand, args.warn_current, args.abort_current, args.abort_temp)
                    continue
                if cmd == "save":
                    save_calibration(args.calibration, target)
                    continue
                if cmd == "rest":
                    target = load_raw_rest(args.calibration)
                    print("target reloaded from saved rest:", fmt(target))
                    current_command = ramp_send(hand, current_command, target, args.max_step_delta, args.rate)
                    telemetry(hand, args.warn_current, args.abort_current, args.abort_temp)
                    continue
                if cmd in {"set", "add"}:
                    if len(parts) != 3:
                        print(f"Expected: {cmd} <channel> <value>")
                        continue
                    try:
                        idx = channel_index(parts[1])
                        value = float(parts[2])
                    except Exception as exc:
                        print(f"Invalid command: {exc}")
                        continue
                    old = target[idx]
                    target[idx] = clamp01(value if cmd == "set" else old + value)
                    print(f"{CHANNEL_NAMES[idx]}: {old:.4f} -> {target[idx]:.4f}")
                    current_command = ramp_send(hand, current_command, target, args.max_step_delta, args.rate)
                    telemetry(hand, args.warn_current, args.abort_current, args.abort_temp)
                    continue
                print("Unknown command. Type 'help'.")
        except Exception:
            print("\n[recovery] sending saved rest after exception/abort")
            hand.apply_rest(args.calibration, settle_s=0.5)
            raise


if __name__ == "__main__":
    raise SystemExit(main())
