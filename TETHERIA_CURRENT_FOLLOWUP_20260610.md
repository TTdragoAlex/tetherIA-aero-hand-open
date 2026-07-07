Subject: Follow-up on Aero Hand GET_CURR current units / >1.3A readings

Hi TetherIA team,

Thanks for the clarification that each servo can peak at about 1.3 A, with a theoretical total of 9.1 A for the hand.

I ran another 100% gesture current profile to check whether our earlier high readings were total hand current or per-servo/channel readings. The new log was:

`logs/servo_current_profile_20260610_115427.csv`

The profiler records both the SDK-converted current and the raw servo current units. The SDK conversion appears to be:

`current_mA = raw_current_units * 6.5`

In this run, the hand completed the full sequence without thermal issues. Max temperature was only 36 C. However, `GET_CURR` again reported individual channels above 1.3 A when using the SDK's mA conversion.

Overall worst sample:

```text
timestamp: 2026-06-10T11:54:39.685
movement: peace_setup_2 / ramp
max_abs_current_ma: 4329.0
max_abs_current_channel: 1 / thumb_flex

channel currents:
ch0 thumb_abd:    -104.0 mA, raw -16
ch1 thumb_flex:   4329.0 mA, raw 666
ch2 thumb_tendon: -2164.5 mA, raw -333
ch3 index:         143.0 mA, raw 22
ch4 middle:          0.0 mA, raw 0
ch5 ring:         3289.0 mA, raw 506
ch6 pinky:        3425.5 mA, raw 527
```

Per-channel maximums from the same run:

```text
ch0 thumb_abd:     936.0 mA, raw 144
ch1 thumb_flex:   4329.0 mA, raw 666
ch2 thumb_tendon: 2164.5 mA, raw 333
ch3 index:        2268.5 mA, raw 349
ch4 middle:       3380.0 mA, raw 520
ch5 ring:         3640.0 mA, raw 560
ch6 pinky:        3425.5 mA, raw 527
```

Samples above 1300 mA by SDK conversion:

```text
ch0 thumb_abd:     0 samples
ch1 thumb_flex:   37 samples
ch2 thumb_tendon:  1 sample
ch3 index:        11 samples
ch4 middle:       35 samples
ch5 ring:         71 samples
ch6 pinky:        36 samples
```

Could you clarify how `GET_CURR` should be interpreted for these servos?

Specifically:

1. Is the SDK's `6.5 mA per raw unit` conversion correct for the Aero Hand servos?
2. If each servo peaks at about 1.3 A, what raw `GET_CURR` value corresponds to 1.3 A?
3. Should the signed `GET_CURR` values be interpreted as actual electrical input current, motor winding current, load/torque proxy, or something else?
4. Should the firmware current limit value `0..1023` map directly to amps, or is it a dimensionless servo limit?

The hand appears to operate correctly mechanically, and temperatures remain low, so this may simply be a units/telemetry interpretation issue. I want to make sure we are using the right threshold before deciding whether full-scale gestures are safe.

Thanks!
