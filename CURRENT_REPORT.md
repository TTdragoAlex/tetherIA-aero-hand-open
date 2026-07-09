# Aero Hand Open 100% Gesture Current Spike Report

## Summary

I am testing an Aero Hand Open with the TetherIA Python SDK and firmware. The hand is mechanically functional: all servos connect, homing completes, and the fingers move correctly through GUI sliders and Python scripts.

The issue is that the official-style 100% gesture sequence appears to create very high current spikes, especially during the peace-sign transition. The worst measured sample was:

```text
4329.0 mA on channel 1 / thumb_flex during peace_setup_2 ramp
```

At that same sample, several other channels were also heavily loaded:

```text
ch1 thumb_flex:    4329.0 mA
ch2 thumb_tendon: -2379.0 mA
ch5 ring:          3042.0 mA
ch6 pinky:         3191.5 mA
```

The hand recovered to open palm afterward. Temperatures stayed low during this short test, with max temperature around `36 C`, so the concern is current/mechanical loading rather than thermal runaway.

## Hardware / Software Context

- Hand: TetherIA Aero Hand Open, right hand
- Controller: Seeed Studio XIAO ESP32S3
- Firmware: TetherIA right-hand firmware, built/flashed locally from the PlatformIO project
- Python SDK: `aero-open-sdk==0.1.0.dev1`
- Host: macOS on Apple Silicon
- Serial baud: `921600`
- Current conversion used by SDK/firmware readout: `1 unit = 6.5 mA`

The hand was homed successfully before testing. All fingers/servos moved correctly in the GUI and via Python.

## Reproduction

The test was based on TetherIA's official `sdk/examples/run_sequence.py` gesture sequence:

```python
trajectory = [
    ([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 1.0),
    ([100.0, 35.0, 23.0, 0.0, 0.0, 0.0, 50.0], 0.5),
    ([100.0, 35.0, 23.0, 0.0, 0.0, 0.0, 50.0], 0.25),
    ([100.0, 42.0, 23.0, 0.0, 0.0, 52.0, 0.0], 0.5),
    ([100.0, 42.0, 23.0, 0.0, 0.0, 52.0, 0.0], 0.25),
    ([83.0, 42.0, 23.0, 0.0, 50.0, 0.0, 0.0], 0.5),
    ([83.0, 42.0, 23.0, 0.0, 50.0, 0.0, 0.0], 0.25),
    ([75.0, 25.0, 30.0, 50.0, 0.0, 0.0, 0.0], 0.5),
    ([75.0, 25.0, 30.0, 50.0, 0.0, 0.0, 0.0], 0.25),
    ([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.5),
    ([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.5),
    ([90.0, 0.0, 0.0, 0.0, 0.0, 90.0, 90.0], 0.5),
    ([90.0, 45.0, 60.0, 0.0, 0.0, 90.0, 90.0], 0.5),
    ([90.0, 45.0, 60.0, 0.0, 0.0, 90.0, 90.0], 1.0),
    ([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.5),
    ([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.5),
    ([0.0, 0.0, 0.0, 0.0, 90.0, 90.0, 0.0], 0.5),
    ([0.0, 0.0, 0.0, 0.0, 90.0, 90.0, 0.0], 1.0),
    ([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.5),
]
```

I wrote a profiling script that samples `GET_POS`, `GET_CURR`, and `GET_TEMP` during ramps and holds, then sends open palm on completion or abort.

Command used:

```bash
./.venv/bin/python scripts/servo_current_profiler.py --run
```

Profiler settings:

```text
pose_scale:        1.00
command rate:      35 Hz
sample period:     0.15 s
hold sample time:  0.35 s per target
report threshold:  1500 mA
hard abort:        3500 mA or 65 C
```

## Results

CSV log:

```text
logs/servo_current_profile_20260609_142903.csv
```

Total samples: `74`

Max temperature during the run: `36 C`

### Overall Worst Sample

```text
movement:       peace_setup_2
phase:          ramp
elapsed:        11.199 s
command_pose:   [90.0, 39.7, 52.9, 0.0, 0.0, 90.0, 90.0]
max current:    4329.0 mA on ch1 / thumb_flex
currents:       [-39.0, 4329.0, -2379.0, 26.0, -45.5, 3042.0, 3191.5] mA
temperatures:   [36.0, 35.0, 34.0, 34.0, 33.0, 34.0, 35.0] C
```

The profiler hard-aborted here and sent open palm.

### Per-Channel Max Absolute Current

```text
ch0 thumb_abd:     1137.5 mA
ch1 thumb_flex:    4329.0 mA
ch2 thumb_tendon:  2379.0 mA
ch3 index:         1839.5 mA
ch4 middle:        1605.5 mA
ch5 ring:          3269.5 mA
ch6 pinky:         3406.0 mA
```

Channels exceeding `1500 mA`:

```text
ch1 thumb_flex
ch2 thumb_tendon
ch3 index
ch4 middle
ch5 ring
ch6 pinky
```

### Worst Movements

```text
peace_setup_2:
  max 4329.0 mA on ch1 / thumb_flex
  channel maxima during movement:
  [169.0, 4329.0, 2379.0, 130.0, 84.5, 3204.5, 3373.5] mA

peace_setup_1:
  max 3406.0 mA on ch6 / pinky
  channel maxima during movement:
  [292.5, 604.5, 175.5, 156.0, 97.5, 3269.5, 3406.0] mA

touch_index:
  max 1839.5 mA on ch3 / index

hold_index:
  max 1768.0 mA on ch3 / index

touch_middle:
  max 1605.5 mA on ch4 / middle

hold_middle:
  max 1592.5 mA on ch4 / middle
```

## Additional Observations

Running scaled versions of the sequence reduced the problem:

- `0.80` pose scale completed the original TetherIA sequence under the chosen target line.
- Exact `1.00` scale repeatedly produced severe loading during the peace-sign transition.

At rest/open palm, current was much lower. After the profiler recovered to open, the final check was:

```text
currents:     [-416.0, 292.5, 32.5, 97.5, -13.0, 39.0, 91.0] mA
temperatures: [36.0, 35.0, 34.0, 34.0, 33.0, 33.0, 35.0] C
```

This suggests the main issue is gesture-dependent mechanical/current loading, not a constant connection/telemetry failure.

## Questions

1. Are the 100% joint targets in the official `run_sequence.py` expected to be safe on a correctly assembled Aero Hand Open?

2. Is it expected that the peace-sign targets:

   ```text
   [90, 0, 0, 0, 0, 90, 90]
   [90, 45, 60, 0, 0, 90, 90]
   ```

   can push ring/pinky and thumb channels into multi-amp current spikes?

3. Is there a recommended mechanical adjustment procedure for reducing this loading?

   Examples:

   ```text
   tendon tension
   finger spring tension
   pulley/string routing
   servo horn/zero position
   homing/trim offsets
   physical hard-stop alignment
   ```

4. Should the official demo be run with reduced torque/current limits, reduced speed, or scaled pose targets?

5. What current levels do you consider acceptable for:

   ```text
   short movement spikes
   sustained gesture holds
   abort threshold
   ```

6. Are there known differences between the demo values and real hardware tolerances, especially for the peace sign and thumb-coupled movements?

7. Is `ch1 / thumb_flex` expected to couple strongly with ring/pinky closure during `peace_setup_2`, or does the measured current pattern suggest a mechanical or calibration problem?

## Requested Guidance

Could you advise whether this looks like:

```text
A. expected behavior for full-scale demo gestures,
B. a mechanical tuning issue,
C. a homing/calibration/trim issue,
D. a firmware/current-limit configuration issue,
E. or something else?
```

If there is a recommended diagnostic procedure, I can run additional tests and provide CSV logs.
