#!/usr/bin/env python3
"""Trim the firmware-side open/extend endpoint for one Aero Hand channel.

This uses the firmware TRIM command (0x03). Unlike raw-rest JSON calibration,
TRIM changes the firmware's extend_count, so it changes where normalized 0.0
maps in the servo's raw position range.
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "lib" / "python3.11" / "site-packages"
if str(SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(SITE_PACKAGES))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import serial  # noqa: E402

from aero_hand_control import AeroHandController, detect_port, fmt  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402
from replay_policy_trace_safe import channel_index  # noqa: E402

TRIM = 0x03
CTRL_POS = 0x11
UINT16_MAX = 65535


def send_frame(ser: serial.Serial, op: int, payload: bytes = b"") -> None:
    if len(payload) > 14:
        raise ValueError("Payload must fit in 14 bytes")
    frame = bytes([op, 0x00]) + payload.ljust(14, b"\x00")
    ser.write(frame)
    ser.flush()


def read_ack(ser: serial.Serial, expected_op: int, timeout_s: float = 1.0) -> bytes:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        header = ser.read(1)
        if not header:
            continue
        if header[0] != expected_op:
            continue
        rest = ser.read(15)
        if len(rest) != 15:
            break
        return header + rest
    raise RuntimeError(f"No TRIM ack received within {timeout_s:.1f}s")


def send_open_pose(ser: serial.Serial) -> None:
    payload = b"".join(struct.pack("<H", 0) for _ in range(7))
    send_frame(ser, CTRL_POS, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Trim firmware extend/open endpoint for one channel.")
    parser.add_argument("--channel", required=True, help="Channel name/index, e.g. ring, pinky, thumb_flex.")
    parser.add_argument(
        "--degrees",
        type=int,
        required=True,
        help="Signed trim in degrees. Try small values first, e.g. +2 or -2.",
    )
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--send-open", action="store_true", help="Send all-zero normalized open pose after trimming.")
    parser.add_argument("--read", action="store_true", help="Read pos/current/temp after trimming.")
    args = parser.parse_args()

    ch = channel_index(args.channel)
    if args.degrees < -180 or args.degrees > 180:
        raise ValueError("Refusing trim outside +/-180 degrees. Use small increments.")

    port = args.port or detect_port()
    payload = struct.pack("<Hh", ch, args.degrees)
    print(f"TRIM channel {ch}:{CHANNEL_NAMES[ch]} by {args.degrees:+d} deg on {port}")

    with serial.Serial(port, args.baud, timeout=0.6, write_timeout=0.6) as ser:
        time.sleep(0.2)
        ser.reset_input_buffer()
        send_frame(ser, TRIM, payload)
        ack = read_ack(ser, TRIM)
        ack_ch, new_extend = struct.unpack("<HH", ack[2:6])
        print(f"ack: channel={ack_ch} new_extend_count={new_extend}")
        if args.send_open:
            send_open_pose(ser)
            time.sleep(0.5)

    if args.read:
        with AeroHandController(port, args.baud) as hand:
            print("pos_norm:", fmt(hand.get_pos_norm()))
            print("curr_ma :", fmt(hand.get_currents_ma(), 1))
            print("temp_c  :", fmt(hand.get_temperatures_c(), 1))

    print("Note: firmware TRIM is persistent. Reverse it with the opposite --degrees if needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
