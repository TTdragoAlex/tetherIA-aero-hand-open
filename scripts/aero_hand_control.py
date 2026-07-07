#!/usr/bin/env python3
"""Small Python helper for controlling the Aero Hand from scripts.

This wraps the installed aero_open_sdk with the raw actuator rest calibration
we found while debugging idle current. It is intentionally lightweight so later
experiments can import it instead of copying serial-protocol code around.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "lib" / "python3.11" / "site-packages"
if str(SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(SITE_PACKAGES))

from serial.tools import list_ports  # noqa: E402
from aero_open_sdk.aero_hand import AeroHand, CTRL_POS  # noqa: E402

UINT16_MAX = 65535
DEFAULT_CALIBRATION_PATH = REPO_ROOT / "aero_hand_calibration.json"
FALLBACK_RAW_REST = [0.163, 0.020, 0.071, 0.0, 0.0, 0.0, 0.0]


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def detect_port() -> str:
    ports = list(list_ports.comports())
    preferred = []
    for port in ports:
        blob = f"{port.device} {port.description} {port.hwid}".lower()
        if "usbmodem" in port.device.lower() or "esp" in blob or "jtag" in blob:
            preferred.append(port.device)
    if len(preferred) == 1:
        return preferred[0]
    if not preferred and len(ports) == 1:
        return ports[0].device
    details = "\n".join(f"  {p.device}\t{p.description}\t{p.hwid}" for p in ports) or "  (none)"
    raise RuntimeError("Could not auto-detect one Aero Hand port. Available ports:\n" + details)


def load_raw_rest(path: Path = DEFAULT_CALIBRATION_PATH) -> list[float]:
    try:
        data = json.loads(path.read_text())
        values = data.get("raw_actuator_rest")
        if isinstance(values, list) and len(values) == 7:
            return [clamp01(v) for v in values]
    except FileNotFoundError:
        pass
    return list(FALLBACK_RAW_REST)


class AeroHandController:
    def __init__(self, port: str | None = None, baudrate: int = 921600):
        self.hand = AeroHand(port or detect_port(), baudrate=baudrate)
        self.hand.ser.timeout = 0.6
        self.hand.ser.write_timeout = 0.6
        time.sleep(1.0)
        self.hand.ser.reset_input_buffer()

    def close(self) -> None:
        self.hand.close()

    def __enter__(self) -> "AeroHandController":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def send_raw_actuators(self, values: Iterable[float]) -> None:
        vals = [clamp01(v) for v in values]
        if len(vals) != 7:
            raise ValueError("Expected 7 raw actuator values")
        payload = [int(round(v * UINT16_MAX)) for v in vals]
        self.hand._send_data(CTRL_POS, payload)

    def apply_rest(self, path: Path = DEFAULT_CALIBRATION_PATH, settle_s: float = 0.4) -> list[float]:
        rest = load_raw_rest(path)
        self.send_raw_actuators(rest)
        time.sleep(settle_s)
        return rest

    def _telemetry_retry(self, label: str, read_fn, attempts: int = 5, gap_s: float = 0.08):
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                vals = read_fn()
                if vals is not None:
                    return vals
            except Exception as exc:  # Keep the recovery path robust around pyserial/SDK hiccups.
                last_error = exc
            try:
                self.hand.ser.reset_input_buffer()
            except Exception:
                pass
            time.sleep(gap_s * attempt)
        if last_error is not None:
            raise RuntimeError(f"{label} failed after {attempts} attempts") from last_error
        raise RuntimeError(f"{label} returned no data after {attempts} attempts")

    def get_pos_norm(self) -> list[float]:
        vals = self._telemetry_retry("GET_POS", self.hand.get_actuations)
        lower = self.hand.actuation_lower_limits
        upper = self.hand.actuation_upper_limits
        return [clamp01((vals[i] - lower[i]) / (upper[i] - lower[i])) for i in range(7)]

    def get_currents_ma(self) -> list[float]:
        vals = self._telemetry_retry("GET_CURR", self.hand.get_actuator_currents)
        return list(vals)

    def get_temperatures_c(self) -> list[float]:
        vals = self._telemetry_retry("GET_TEMP", self.hand.get_actuator_temperatures)
        return list(vals)


def fmt(values: Iterable[float], digits: int = 3) -> str:
    return "[" + ", ".join(f"{v:.{digits}f}" for v in values) + "]"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply/read Aero Hand raw actuator calibration from Python.")
    parser.add_argument("--port", help="Serial port. Auto-detected if omitted.")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--apply-rest", action="store_true", help="Send saved raw rest before reading telemetry.")
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION_PATH)
    parser.add_argument("--warn-current", type=float, default=250.0, help="Warn for channels above this absolute current in mA.")
    parser.add_argument("--warn-temp", type=float, default=55.0, help="Warn for channels above this temperature in C.")
    args = parser.parse_args()

    with AeroHandController(args.port, args.baud) as hand:
        if args.apply_rest:
            rest = hand.apply_rest(args.calibration)
            print("applied raw rest:", fmt(rest))
        pos = hand.get_pos_norm()
        curr = hand.get_currents_ma()
        temp = hand.get_temperatures_c()
        print("pos_norm:", fmt(pos))
        print("curr_ma:", fmt(curr, 1))
        print("temp_c:", fmt(temp, 1))
        hot_curr = [i for i, value in enumerate(curr) if abs(value) >= args.warn_current]
        hot_temp = [i for i, value in enumerate(temp) if value >= args.warn_temp]
        if hot_curr:
            print(f"warn_current_channels: {hot_curr} (threshold {args.warn_current:.1f} mA)")
        if hot_temp:
            print(f"warn_temp_channels: {hot_temp} (threshold {args.warn_temp:.1f} C)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
