#!/usr/bin/env python3
"""Aero Hand idle-current probe.

This talks to the same protocol as the GUI, but logs targets, positions,
currents, and temperatures so idle-current issues can be debugged from data.
"""

import argparse
import csv
import math
import os
import struct
import sys
import time
from dataclasses import dataclass
from datetime import datetime

from serial.tools import list_ports

# Let this script run from the repo root without installing anything globally.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_PACKAGES = os.path.join(REPO_ROOT, ".venv", "lib", "python3.11", "site-packages")
if SITE_PACKAGES not in sys.path:
    sys.path.insert(0, SITE_PACKAGES)

from aero_open_sdk.aero_hand import AeroHand, CTRL_POS, GET_CURR, GET_POS, GET_TEMP  # noqa: E402

UINT16_MAX = 65535
CHANNELS = 7


@dataclass
class Telemetry:
    pos_norm: list[float]
    curr_ma: list[float]
    temp_c: list[float]


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def parse_floats(text: str, expected: int, name: str) -> list[float]:
    vals = [float(x.strip()) for x in text.split(",") if x.strip()]
    if len(vals) != expected:
        raise argparse.ArgumentTypeError(f"{name} must have {expected} comma-separated values")
    return vals


def parse_channels(text: str) -> list[int]:
    vals = [int(x.strip()) for x in text.split(",") if x.strip()]
    if not vals:
        raise argparse.ArgumentTypeError("at least one channel is required")
    bad = [v for v in vals if v < 0 or v >= CHANNELS]
    if bad:
        raise argparse.ArgumentTypeError(f"channels must be 0..6, got {bad}")
    return vals


def detect_port() -> str:
    ports = list(list_ports.comports())
    preferred = []
    for p in ports:
        blob = f"{p.device} {p.description} {p.hwid}".lower()
        if "usbmodem" in p.device.lower() or "esp" in blob or "jtag" in blob:
            preferred.append(p.device)
    if len(preferred) == 1:
        return preferred[0]
    if not preferred and len(ports) == 1:
        return ports[0].device
    details = "\n".join(f"  {p.device}\t{p.description}\t{p.hwid}" for p in ports) or "  (none)"
    raise RuntimeError("Could not auto-detect a single hand port. Available ports:\n" + details)


def frame(opcode: int, payload: list[int] | None = None) -> bytes:
    values = [0] * CHANNELS if payload is None else payload
    if len(values) != CHANNELS:
        raise ValueError("payload must contain 7 values")
    return struct.pack("<2B7H", opcode & 0xFF, 0, *(int(v) & 0xFFFF for v in values))


def request_frame(hand: AeroHand, opcode: int, fmt: str, attempts: int = 3) -> tuple[int, ...]:
    for _ in range(attempts):
        hand.ser.reset_input_buffer()
        hand.ser.write(frame(opcode))
        hand.ser.flush()
        resp = hand.ser.read(16)
        if len(resp) == 16:
            data = struct.unpack(fmt, resp)
            if data[0] == opcode and data[1] == 0:
                return data
        time.sleep(0.03)
    raise TimeoutError(f"No valid response for opcode 0x{opcode:02X}")


def read_telemetry(hand: AeroHand) -> Telemetry:
    pos = request_frame(hand, GET_POS, "<2B7H")[2:]
    curr = request_frame(hand, GET_CURR, "<2B7h")[2:]
    temp = request_frame(hand, GET_TEMP, "<2B7H")[2:]
    return Telemetry(
        pos_norm=[v / UINT16_MAX for v in pos],
        curr_ma=[v * 6.5 for v in curr],
        temp_c=[float(v) for v in temp],
    )


def slider_to_command_u16(hand: AeroHand, sliders: list[float]) -> tuple[list[int], list[float], list[float]]:
    """Return raw actuator command matching the GUI's slider TX loop."""
    sliders = [clamp01(v) for v in sliders]
    joint_values = [
        hand.joint_lower_limits[i] + (hand.joint_upper_limits[i] - hand.joint_lower_limits[i]) * sliders[i]
        for i in range(CHANNELS)
    ]
    positions16 = hand.convert_seven_joints_to_sixteen(joint_values)
    positions16 = [
        max(hand.joint_lower_limits[i], min(positions16[i], hand.joint_upper_limits[i]))
        for i in range(16)
    ]
    actuations = hand.joints_to_actuations_model.hand_actuations(positions16)
    cmd_norm = [
        clamp01((actuations[i] - hand.actuation_lower_limits[i]) /
                (hand.actuation_upper_limits[i] - hand.actuation_lower_limits[i]))
        for i in range(CHANNELS)
    ]
    cmd_u16 = [int(round(v * UINT16_MAX)) for v in cmd_norm]
    return cmd_u16, cmd_norm, joint_values


def send_slider_target(hand: AeroHand, sliders: list[float]) -> tuple[list[int], list[float], list[float]]:
    cmd_u16, cmd_norm, joint_values = slider_to_command_u16(hand, sliders)
    hand.ser.write(frame(CTRL_POS, cmd_u16))
    hand.ser.flush()
    return cmd_u16, cmd_norm, joint_values


def send_actuator_target(hand: AeroHand, actuator_norm: list[float]) -> tuple[list[int], list[float], list[float]]:
    cmd_norm = [clamp01(v) for v in actuator_norm]
    cmd_u16 = [int(round(v * UINT16_MAX)) for v in cmd_norm]
    hand.ser.write(frame(CTRL_POS, cmd_u16))
    hand.ser.flush()
    return cmd_u16, cmd_norm, [float("nan")] * CHANNELS


def send_target(hand: AeroHand, target: list[float], space: str) -> tuple[list[int], list[float], list[float]]:
    if space == "actuator":
        return send_actuator_target(hand, target)
    return send_slider_target(hand, target)


def ramp_to(hand: AeroHand, start: list[float], target: list[float], step: float, period: float, space: str) -> None:
    max_delta = max(abs(target[i] - start[i]) for i in range(CHANNELS))
    steps = max(1, int(math.ceil(max_delta / max(step, 1e-6))))
    for s in range(1, steps + 1):
        alpha = s / steps
        point = [start[i] + (target[i] - start[i]) * alpha for i in range(CHANNELS)]
        send_target(hand, point, space)
        time.sleep(period)


def average_samples(hand: AeroHand, samples: int, sample_gap: float) -> Telemetry:
    pos_acc = [0.0] * CHANNELS
    cur_acc = [0.0] * CHANNELS
    tmp_acc = [0.0] * CHANNELS
    for i in range(samples):
        t = read_telemetry(hand)
        for ch in range(CHANNELS):
            pos_acc[ch] += t.pos_norm[ch]
            cur_acc[ch] += t.curr_ma[ch]
            tmp_acc[ch] += t.temp_c[ch]
        if i != samples - 1:
            time.sleep(sample_gap)
    return Telemetry(
        pos_norm=[v / samples for v in pos_acc],
        curr_ma=[v / samples for v in cur_acc],
        temp_c=[v / samples for v in tmp_acc],
    )


def score_currents(curr_ma: list[float], channels: list[int] | None = None) -> float:
    channels = list(range(CHANNELS)) if channels is None else channels
    return sum(abs(curr_ma[ch]) for ch in channels)


def fmt(vals: list[float], digits: int = 3) -> str:
    return "[" + ", ".join(f"{v:.{digits}f}" for v in vals) + "]"


def write_row(writer, mode, channel, slider_target, cmd_norm, telemetry):
    row = {
        "timestamp": time.time(),
        "mode": mode,
        "channel": "" if channel is None else channel,
        "score_all_abs_ma": score_currents(telemetry.curr_ma),
        "max_abs_current_ma": max(abs(v) for v in telemetry.curr_ma),
        "max_temp_c": max(telemetry.temp_c),
    }
    for i in range(CHANNELS):
        row[f"slider_{i}"] = slider_target[i]
        row[f"cmd_norm_{i}"] = cmd_norm[i]
        row[f"pos_norm_{i}"] = telemetry.pos_norm[i]
        row[f"err_norm_{i}"] = telemetry.pos_norm[i] - cmd_norm[i]
        row[f"curr_ma_{i}"] = telemetry.curr_ma[i]
        row[f"temp_c_{i}"] = telemetry.temp_c[i]
    writer.writerow(row)
    return row


def make_writer(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fields = ["timestamp", "mode", "channel", "score_all_abs_ma", "max_abs_current_ma", "max_temp_c"]
    for i in range(CHANNELS):
        fields += [f"slider_{i}", f"cmd_norm_{i}", f"pos_norm_{i}", f"err_norm_{i}", f"curr_ma_{i}", f"temp_c_{i}"]
    fh = open(path, "w", newline="")
    return fh, csv.DictWriter(fh, fieldnames=fields)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Aero Hand idle current without using the GUI.")
    parser.add_argument("--port", help="Serial port, e.g. /dev/cu.usbmodem101. Auto-detected if omitted.")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--space", choices=("slider", "actuator"), default="slider",
                        help="Target space. slider matches the GUI. actuator sends raw normalized servo targets.")
    parser.add_argument("--baseline", type=lambda s: parse_floats(s, CHANNELS, "baseline"),
                        default=[0.15, 0.036, 0.073, 0.0, 0.0, 0.0, 0.0],
                        help="7 comma-separated baseline values in the selected --space.")
    parser.add_argument("--channels", type=parse_channels, default=[0, 1, 2],
                        help="Comma-separated channels to sweep. Default: 0,1,2")
    parser.add_argument("--span", type=float, default=0.06, help="Sweep +/- span around baseline for each channel.")
    parser.add_argument("--step", type=float, default=0.01, help="Sweep step in normalized slider units.")
    parser.add_argument("--settle", type=float, default=0.7, help="Seconds to wait after each target before sampling.")
    parser.add_argument("--samples", type=int, default=3, help="Telemetry samples per target.")
    parser.add_argument("--sample-gap", type=float, default=0.08)
    parser.add_argument("--ramp-step", type=float, default=0.01, help="Max normalized slider jump per ramp frame.")
    parser.add_argument("--ramp-period", type=float, default=0.03, help="Seconds between ramp frames.")
    parser.add_argument("--read-only", action="store_true", help="Only read GET_POS/GET_CURR/GET_TEMP; do not move.")
    parser.add_argument("--hold", type=float, default=0.0, help="Hold baseline for N seconds and log repeated samples.")
    parser.add_argument("--max-current", type=float, default=900.0, help="Abort if any abs current exceeds this mA.")
    parser.add_argument("--max-temp", type=float, default=55.0, help="Abort if any temp exceeds this C.")
    parser.add_argument("--log", default=None, help="CSV log path. Default: logs/aero_idle_probe_YYYYmmdd_HHMMSS.csv")
    args = parser.parse_args()

    port = args.port or detect_port()
    log_path = args.log or os.path.join(REPO_ROOT, "logs", f"aero_idle_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    print(f"Opening {port} @ {args.baud}. Close the GUI first if this fails.")
    hand = AeroHand(port=port, baudrate=args.baud)
    hand.ser.timeout = 0.6
    hand.ser.write_timeout = 0.6

    try:
        if args.read_only:
            telemetry = average_samples(hand, args.samples, args.sample_gap)
            print("GET_POS norm:", fmt(telemetry.pos_norm))
            print("GET_CURR mA:", fmt(telemetry.curr_ma, 1))
            print("GET_TEMP C:", fmt(telemetry.temp_c, 1))
            return 0

        baseline = [clamp01(v) for v in args.baseline]
        print(f"Baseline {args.space} target:", fmt(baseline))
        print("Safety: keep the hand clear and be ready to cut servo power if anything looks wrong.")

        fh, writer = make_writer(log_path)
        with fh:
            writer.writeheader()
            current_slider = baseline[:]
            ramp_to(hand, current_slider, baseline, args.ramp_step, args.ramp_period, args.space)
            current_slider = baseline[:]
            time.sleep(args.settle)
            cmd_u16, cmd_norm, _ = send_target(hand, baseline, args.space)
            telemetry = average_samples(hand, args.samples, args.sample_gap)
            rows = [write_row(writer, "baseline", None, baseline, cmd_norm, telemetry)]
            print(f"baseline score={rows[-1]['score_all_abs_ma']:.1f}mA curr={fmt(telemetry.curr_ma, 1)} pos={fmt(telemetry.pos_norm)} cmd={fmt(cmd_norm)}")

            if max(abs(v) for v in telemetry.curr_ma) > args.max_current or max(telemetry.temp_c) > args.max_temp:
                raise RuntimeError("Baseline exceeded safety limits; aborting before sweep.")

            if args.hold > 0:
                end = time.monotonic() + args.hold
                while time.monotonic() < end:
                    send_target(hand, baseline, args.space)
                    time.sleep(args.settle)
                    telemetry = average_samples(hand, args.samples, args.sample_gap)
                    rows.append(write_row(writer, "hold", None, baseline, cmd_norm, telemetry))
                    print(f"hold score={rows[-1]['score_all_abs_ma']:.1f}mA curr={fmt(telemetry.curr_ma, 1)} pos={fmt(telemetry.pos_norm)}")
                    if max(abs(v) for v in telemetry.curr_ma) > args.max_current or max(telemetry.temp_c) > args.max_temp:
                        raise RuntimeError("Safety limit exceeded during hold.")

            if args.hold <= 0:
                for ch in args.channels:
                    lo = clamp01(baseline[ch] - args.span)
                    hi = clamp01(baseline[ch] + args.span)
                    count = int(math.floor((hi - lo) / args.step + 0.5)) + 1
                    values = [lo + i * args.step for i in range(count)]
                    if values[-1] < hi - 1e-9:
                        values.append(hi)
                    print(f"Sweeping channel {ch}: {lo:.3f}..{hi:.3f} step {args.step:.3f}")
                    for value in values:
                        target = baseline[:]
                        target[ch] = clamp01(value)
                        ramp_to(hand, current_slider, target, args.ramp_step, args.ramp_period, args.space)
                        current_slider = target[:]
                        time.sleep(args.settle)
                        _cmd_u16, cmd_norm, _ = send_target(hand, target, args.space)
                        telemetry = average_samples(hand, args.samples, args.sample_gap)
                        row = write_row(writer, "sweep", ch, target, cmd_norm, telemetry)
                        rows.append(row)
                        print(
                            f"ch{ch} slider={target[ch]:.3f} score={row['score_all_abs_ma']:.1f}mA "
                            f"curr={fmt(telemetry.curr_ma, 1)} pos={fmt(telemetry.pos_norm)} cmd={fmt(cmd_norm)}"
                        )
                        if max(abs(v) for v in telemetry.curr_ma) > args.max_current or max(telemetry.temp_c) > args.max_temp:
                            raise RuntimeError("Safety limit exceeded during sweep.")

            best = sorted(rows, key=lambda r: r["score_all_abs_ma"])[:10]
            print("\nTop low-current rows:")
            for i, row in enumerate(best, 1):
                sliders = [row[f"slider_{ch}"] for ch in range(CHANNELS)]
                currents = [row[f"curr_ma_{ch}"] for ch in range(CHANNELS)]
                print(f"{i:02d}. score={row['score_all_abs_ma']:.1f}mA mode={row['mode']} ch={row['channel']} sliders={fmt(sliders)} curr={fmt(currents, 1)}")
            print(f"\nCSV log: {log_path}")

    finally:
        try:
            hand.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
