# Aero Hand Software Setup

This workspace uses a local Python virtual environment at `.venv` so the Aero Hand SDK stays separate from Anaconda/system Python.

## Installed

- Python: 3.11.9
- Package: `aero-open-sdk==0.1.0.dev1`
- GUI command: `./launch_gui.sh`

## Verify SDK

```sh
.venv/bin/python scripts/smoke_test.py
```

Expected output includes:

```text
aero_open_sdk import OK
AeroHand import OK
```

## List Serial Ports

```sh
.venv/bin/python scripts/list_ports.py
```

The likely Aero Hand port found during setup was:

```text
/dev/cu.usbmodem1101	USB JTAG/serial debug unit	USB VID:PID=303A:1001 SER=E0:72:A1:F9:91:64 LOCATION=1-1
```

On macOS, prefer `/dev/cu.*` paths for initiating serial connections from your application.

## Launch GUI

```sh
./launch_gui.sh
```

In the GUI:

1. Click Refresh near Port selection.
2. Select `/dev/cu.usbmodem1101` if it is not auto-selected.
3. Make sure the hand is in a safe, unobstructed position.
4. Press Homing before testing motion.
5. Use the sliders gently to verify individual motion.

## Python Example

```python
from aero_open_sdk.aero_hand import AeroHand

hand = AeroHand(port='/dev/cu.usbmodem1101')
```

Only run movement examples when the hand is safely positioned and homed.

## macOS GUI Patch

The PyPI SDK currently calls Tk's `-zoomed` window attribute, which is not supported by macOS Tk. `./launch_gui.sh` runs `scripts/patch_aero_gui_macos.py` before launching so the GUI uses a macOS-safe fullscreen-sized window instead.

## Firmware Flashed

A fresh Seeed Studio XIAO ESP32S3 board was flashed with the official TetherIA right-hand firmware binary:

```text
firmware-bin/firmware_v0.2.0_righthand.bin
```

Flash command used:

```sh
.venv/bin/python -m esptool --chip esp32s3 -p /dev/cu.usbmodem1101 -b 921600 write-flash 0x10000 firmware-bin/firmware_v0.2.0_righthand.bin
```

Result:

```text
Wrote 334384 bytes at 0x00010000
Hash of data verified
```

Post-flash serial check:

```text
Opened /dev/cu.usbmodem1101 at 921600 OK
```

Keep servos disconnected until you are ready for controlled one-servo testing.

## Idle Current / Rest Calibration

The thumb can draw high idle current when the command target differs from the actuator position where the mechanism actually settles. The GUI now includes a raw actuator calibration mode for this.

Recommended workflow:

1. Launch the GUI with `./launch_gui.sh`.
2. Connect to the hand.
3. Click `Raw actuator sliders (calibration)`.
4. Click `Load Current GET_POS` to load and immediately send the current physical actuator pose as the raw target.
5. Confirm the logged `GET_CURR` values are acceptable.

This workflow is intentionally stateless: it does not save a rest pose. The hand has hysteresis, so matching the current physical pose is usually clearer than reusing an old saved pose. Python scripts can use `scripts/aero_hand_control.py` for telemetry and safety warnings.

Example Python-side check:

```bash
./.venv/bin/python scripts/aero_hand_control.py --apply-rest
```

### Current Findings From Calibration

Raw actuator calibration fixes command/position mismatch, but it does not remove every idle current source. In the current hand state, channel 1 stayed around 250-270 mA even when commanded at its measured lower-position rest. Small raw target sweeps did not reduce that current; commanding above zero often made it worse. This points to mechanical preload, a lower stop, tendon tension, or trim/homing offset rather than a GUI math problem.

Approximate current baseline after saving current rest:

```text
GET_POS:  [0.014, 0.000, 0.055, 0.000, 0.000, 0.000, 0.000]
GET_CURR: [~0-10, ~260, ~0, ~130-150, ~0-15, ~30-40, ~85-100] mA
TEMP:     mid/high 30s C during testing
```

This is thermally safe in the observed tests, but channel 1 should be watched. If lower idle current is required, the next experiment should be mechanical/trim-focused, not another GUI mapping change.

## Python Gesture Smoke Test

The first Python motion test is `scripts/gesture_smoke_test.py`. It uses conservative joint-space poses and prints `GET_POS`, `GET_CURR`, and `GET_TEMP` after each pose.

Dry run, no motion:

```bash
./.venv/bin/python scripts/gesture_smoke_test.py
```

Actual movement test:

```bash
./.venv/bin/python scripts/gesture_smoke_test.py --run
```

The script warns above 450 mA by default and aborts above 2500 mA or 60 C. Short current spikes are expected; sustained heat is the stronger danger signal. Keep the GUI disconnected while running Python scripts so the serial port is not already in use.

## TetherIA Gesture Sequence

The official TetherIA example was copied to:

```bash
upstream/tetheria-sdk-examples/run_sequence.py
```

The safer local wrapper is:

```bash
./.venv/bin/python scripts/tetheria_run_sequence_safe.py --run
```

The default `--pose-scale` is now `0.85`. `--pose-scale 0.85` multiplies the compact 7-joint angle targets by 85%. For example, a 90 degree target becomes 76.5 degrees before the SDK converts joint angles into actuator commands.

Observed result: the exact 100% sequence hit hard-stop-like current on ring/pinky during the peace sign. The autoscaler accepted 80% for the original TetherIA sequence, with some channels still briefly reaching roughly 1.4 A.

Current interpretation for this hand:

```text
< 350 mA: good / normal
350-800 mA: loaded but acceptable briefly
800-1300 mA: caution, short motion only
1300-1500 mA: stall-ish zone, avoid sustained holding
> 1500 mA: bad if sustained, reduce pose or stop
> 2500 mA: hard abort threshold
Temp >= 55 C: warning
Temp >= 60 C: stop
```

## Auto-Scaling Gesture Test

Use the autoscaler to find a scale that completes TetherIA's gesture sequence below a target current/temperature line.

Dry run, no hand needed:

```bash
./.venv/bin/python scripts/tetheria_autoscale_sequence.py
```

Actual movement test, hand connected and clear:

```bash
./.venv/bin/python scripts/tetheria_autoscale_sequence.py --run
```

Defaults:

```text
start scale: 1.00
minimum scale: 0.55
step: 0.05
accept if max current <= 1500 mA and max temp <= 50 C
hard abort if current >= 2500 mA or temp >= 60 C
```

## Named Gesture API

Reusable named gestures live in:

```bash
scripts/aero_gestures.py
```

Dry run, no hand needed:

```bash
./.venv/bin/python scripts/aero_gestures.py
```

Run the full named-gesture demo with telemetry CSV logging:

```bash
./.venv/bin/python scripts/aero_gestures.py --run
```

Run one gesture:

```bash
./.venv/bin/python scripts/aero_gestures.py --run --gesture peace
```

Python usage:

```python
from aero_gestures import AeroGestureController

with AeroGestureController() as hand:
    hand.open()
    hand.pinch("index")
    hand.peace()
    hand.rockstar()
```

## Servo Current Profiling

Use this when the goal is reaching 100% commands and understanding what blocks it.

Dry run, no hand needed:

```bash
./.venv/bin/python scripts/servo_current_profiler.py
```

Profile full 100% commands with detailed CSV logging:

```bash
./.venv/bin/python scripts/servo_current_profiler.py --run
```

What it reports:

- worst current sample overall
- per-servo maximum absolute current
- which servos exceeded the target current line
- worst movements/holds by current
- final CSV path under `logs/`

Default thresholds:

```text
target/report current: 1500 mA
console warning: 800 mA
hard abort: 3500 mA or 60 C
```

The hard abort is intentionally higher than the target line so the profiler can
measure short overloaded regions, but it still sends open palm if a sample
crosses the emergency threshold.
