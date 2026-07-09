#!/usr/bin/env python3
"""Reusable named-gesture API for the Aero Hand.

This module is intentionally small and script-friendly. It wraps the SDK with
named gestures, smooth interpolation, telemetry checks, and CSV logging.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, fmt  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402


LOG_DIR = REPO_ROOT / "logs"
DEFAULT_POSE_SCALE = 0.85


@dataclass(frozen=True)
class Gesture:
    name: str
    pose: list[float]
    hold_s: float = 0.6
    scale: float = DEFAULT_POSE_SCALE

    def scaled_pose(self) -> list[float]:
        return [value * self.scale for value in self.pose]


GESTURES: dict[str, Gesture] = {
    "open": Gesture("open", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], hold_s=0.5, scale=1.0),
    "pinch_index": Gesture("pinch_index", [75.0, 25.0, 30.0, 50.0, 0.0, 0.0, 0.0], hold_s=0.5),
    "pinch_middle": Gesture("pinch_middle", [83.0, 42.0, 23.0, 0.0, 50.0, 0.0, 0.0], hold_s=0.5),
    "pinch_ring": Gesture("pinch_ring", [100.0, 42.0, 23.0, 0.0, 0.0, 52.0, 0.0], hold_s=0.5),
    "pinch_pinky": Gesture("pinch_pinky", [100.0, 35.0, 23.0, 0.0, 0.0, 0.0, 50.0], hold_s=0.5),
    "peace": Gesture("peace", [90.0, 45.0, 60.0, 0.0, 0.0, 90.0, 90.0], hold_s=1.0),
    "rockstar": Gesture("rockstar", [0.0, 0.0, 0.0, 0.0, 90.0, 90.0, 0.0], hold_s=1.0),
}


DEMO_SEQUENCE = [
    "open",
    "pinch_pinky",
    "open",
    "pinch_ring",
    "open",
    "pinch_middle",
    "open",
    "pinch_index",
    "open",
    "peace",
    "open",
    "rockstar",
    "open",
]


def lerp(start: list[float], end: list[float], alpha: float) -> list[float]:
    return [start[i] + (end[i] - start[i]) * alpha for i in range(7)]


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class GestureLogger:
    def __init__(self, path: Path | None):
        self.path = path
        self.file = None
        self.writer = None

    def __enter__(self) -> "GestureLogger":
        if self.path is None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("w", newline="")
        fieldnames = ["timestamp", "label", "max_abs_current_ma", "max_temp_c"]
        for idx, name in enumerate(CHANNEL_NAMES):
            fieldnames.extend([
                f"pos_{idx}_{name}",
                f"curr_ma_{idx}_{name}",
                f"temp_c_{idx}_{name}",
            ])
        self.writer = csv.DictWriter(self.file, fieldnames=fieldnames)
        self.writer.writeheader()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.file is not None:
            self.file.close()

    def log(self, label: str, pos: list[float], curr: list[float], temp: list[float]) -> None:
        if self.writer is None:
            return
        row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "label": label,
            "max_abs_current_ma": max(abs(value) for value in curr),
            "max_temp_c": max(temp),
        }
        for idx, name in enumerate(CHANNEL_NAMES):
            row[f"pos_{idx}_{name}"] = pos[idx]
            row[f"curr_ma_{idx}_{name}"] = curr[idx]
            row[f"temp_c_{idx}_{name}"] = temp[idx]
        self.writer.writerow(row)
        if self.file is not None:
            self.file.flush()


class AeroGestureController:
    def __init__(
        self,
        port: str | None = None,
        baudrate: int = 921600,
        rate_hz: float = 50.0,
        ramp_s: float = 0.7,
        warn_current: float = 450.0,
        abort_current: float = 2500.0,
        warn_temp: float = 55.0,
        abort_temp: float = 65.0,
        log_path: Path | None = None,
    ):
        self.controller = AeroHandController(port, baudrate)
        self.rate_hz = rate_hz
        self.ramp_s = ramp_s
        self.warn_current = warn_current
        self.abort_current = abort_current
        self.warn_temp = warn_temp
        self.abort_temp = abort_temp
        self.last_pose = [0.0] * 7
        self.logger = GestureLogger(log_path)

    def __enter__(self) -> "AeroGestureController":
        self.logger.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.open(hold_s=0.3)
        finally:
            self.logger.__exit__(exc_type, exc, tb)
            self.controller.close()

    def telemetry(self, label: str) -> tuple[list[float], list[float], list[float]]:
        pos = self.controller.get_pos_norm()
        curr = self.controller.get_currents_ma()
        temp = self.controller.get_temperatures_c()
        self.logger.log(label, pos, curr, temp)
        print(f"[{label}] pos={fmt(pos)} curr={fmt(curr, 1)} temp={fmt(temp, 1)}")

        current_warn = [i for i, value in enumerate(curr) if abs(value) >= self.warn_current]
        temp_warn = [i for i, value in enumerate(temp) if value >= self.warn_temp]
        if current_warn:
            named = ", ".join(f"{i}:{CHANNEL_NAMES[i]}={curr[i]:.1f}mA" for i in current_warn)
            print(f"[{label}] WARN current: {named}")
        if temp_warn:
            named = ", ".join(f"{i}:{CHANNEL_NAMES[i]}={temp[i]:.1f}C" for i in temp_warn)
            print(f"[{label}] WARN temp: {named}")

        current_abort = [i for i, value in enumerate(curr) if abs(value) >= self.abort_current]
        temp_abort = [i for i, value in enumerate(temp) if value >= self.abort_temp]
        if current_abort or temp_abort:
            self.controller.hand.set_joint_positions([0.0] * 7)
            parts = []
            if current_abort:
                parts.append("current " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={curr[i]:.1f}mA" for i in current_abort))
            if temp_abort:
                parts.append("temp " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={temp[i]:.1f}C" for i in temp_abort))
            raise RuntimeError("Safety abort: " + "; ".join(parts))
        return pos, curr, temp

    def move_to(self, name: str, pose: list[float], hold_s: float = 0.5) -> None:
        steps = max(1, int(self.ramp_s * self.rate_hz))
        print(f"\nMoving to {name}: {fmt(pose, 1)}")
        for step in range(1, steps + 1):
            self.controller.hand.set_joint_positions(lerp(self.last_pose, pose, step / steps))
            time.sleep(1.0 / self.rate_hz)
        self.last_pose = pose[:]
        time.sleep(hold_s)
        self.telemetry(name)

    def gesture(self, name: str, scale: float | None = None, hold_s: float | None = None) -> None:
        if name not in GESTURES:
            raise KeyError(f"Unknown gesture '{name}'. Available: {', '.join(sorted(GESTURES))}")
        gesture = GESTURES[name]
        effective_scale = gesture.scale if scale is None else scale
        pose = [value * effective_scale for value in gesture.pose]
        self.move_to(name, pose, gesture.hold_s if hold_s is None else hold_s)

    def open(self, hold_s: float = 0.5) -> None:
        self.move_to("open", [0.0] * 7, hold_s)

    def pinch(self, finger: str, hold_s: float | None = None) -> None:
        aliases = {"index": "pinch_index", "middle": "pinch_middle", "ring": "pinch_ring", "pinky": "pinch_pinky"}
        if finger not in aliases:
            raise KeyError("finger must be one of: index, middle, ring, pinky")
        self.gesture(aliases[finger], hold_s=hold_s)

    def peace(self, hold_s: float | None = None) -> None:
        self.gesture("peace", hold_s=hold_s)

    def rockstar(self, hold_s: float | None = None) -> None:
        self.gesture("rockstar", hold_s=hold_s)

    def run_demo(self) -> None:
        self.telemetry("initial")
        for name in DEMO_SEQUENCE:
            self.gesture(name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run named Aero Hand gestures with telemetry logging.")
    parser.add_argument("--run", action="store_true", help="Actually move the hand. Omit for dry run.")
    parser.add_argument("--gesture", choices=sorted(GESTURES), help="Run one gesture instead of the full demo.")
    parser.add_argument("--demo", action="store_true", help="Run the full demo sequence.")
    parser.add_argument("--port", help="Serial port. Auto-detected if omitted.")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--rate", type=float, default=50.0)
    parser.add_argument("--ramp", type=float, default=0.7)
    parser.add_argument("--log", type=Path, default=None, help="CSV log path. Defaults to logs/aero_gestures_<timestamp>.csv when --run.")
    parser.add_argument("--warn-current", type=float, default=450.0)
    parser.add_argument("--abort-current", type=float, default=2500.0)
    parser.add_argument("--warn-temp", type=float, default=55.0)
    parser.add_argument("--abort-temp", type=float, default=65.0)
    args = parser.parse_args()

    requested = "demo" if args.demo or args.gesture is None else args.gesture
    print(f"Requested gesture run: {requested}")
    print(f"Available gestures: {', '.join(sorted(GESTURES))}")
    if not args.run:
        print("\nDry run only. Re-run with --run to move the hand.")
        return 0

    log_path = args.log or (LOG_DIR / f"aero_gestures_{timestamp()}.csv")
    print(f"Logging telemetry to: {log_path}")
    with AeroGestureController(
        port=args.port,
        baudrate=args.baud,
        rate_hz=args.rate,
        ramp_s=args.ramp,
        warn_current=args.warn_current,
        abort_current=args.abort_current,
        warn_temp=args.warn_temp,
        abort_temp=args.abort_temp,
        log_path=log_path,
    ) as hand:
        if args.gesture:
            hand.telemetry("initial")
            hand.gesture(args.gesture)
        else:
            hand.run_demo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
