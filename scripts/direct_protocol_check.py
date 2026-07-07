#!/usr/bin/env python3
import argparse
import struct
import sys
import time

import serial
from serial.tools import list_ports

GET_TEMP = 0x25
SET_ID = 0x02


def frame(opcode, payload=None):
    values = [0] * 7 if payload is None else payload
    if len(values) != 7:
        raise ValueError('payload must contain 7 uint16 values')
    return struct.pack('<2B7H', opcode & 0xFF, 0x00, *[v & 0xFFFF for v in values])


def read_frame(ser, label):
    data = ser.read(16)
    print(f'{label} raw:', data.hex(' '), f'len={len(data)}')
    if len(data) != 16:
        return None
    return struct.unpack('<2B7H', data)


def main():
    parser = argparse.ArgumentParser(description='Bypass GUI and test Aero Hand 16-byte serial protocol directly.')
    parser.add_argument('port', nargs='?', help='Serial port, for example /dev/cu.usbmodem1101')
    parser.add_argument('--baud', type=int, default=921600)
    parser.add_argument('--set-id', type=int, default=None, help='Optional new servo ID to request')
    parser.add_argument('--current', type=int, default=1023, help='Current limit for --set-id')
    args = parser.parse_args()

    if not args.port:
        print('No port provided. Available ports:')
        for port in list_ports.comports():
            print(f'  {port.device}\t{port.description}\t{port.hwid}')
        return 2

    with serial.Serial(args.port, args.baud, timeout=1.0, write_timeout=1.0) as ser:
        time.sleep(0.2)
        ser.reset_input_buffer()

        print(f'Opened {args.port} @ {args.baud}')
        ser.write(frame(GET_TEMP))
        ser.flush()
        parsed = read_frame(ser, 'GET_TEMP')
        if parsed:
            print('GET_TEMP parsed:', parsed)
            print('GET_TEMP values:', list(parsed[2:]))

        if args.set_id is not None:
            ser.reset_input_buffer()
            payload = [0] * 7
            payload[0] = args.set_id & 0xFF
            payload[1] = args.current & 0x03FF
            ser.write(frame(SET_ID, payload))
            ser.flush()
            parsed = read_frame(ser, 'SET_ID')
            if parsed:
                print('SET_ID parsed:', parsed)
                print('SET_ID old/new/current:', parsed[2], parsed[3], parsed[4])

    return 0


if __name__ == '__main__':
    sys.exit(main())
