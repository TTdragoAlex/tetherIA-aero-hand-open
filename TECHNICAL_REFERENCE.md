# Technical Reference

This file keeps important project facts that are too detailed for the README but
too important to lose.

## Command Order And Action Semantics

Physical hand command order:

```text
[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]
```

Original simulation action order:

```text
[index, middle, ring, pinky, thumb_abd, thumb_flex, thumb_tendon]
```

Never assume these orders match.

Current hardware01 policy/replay convention uses real-order `u` commands:

- `0 = open/release`
- `0.5 = home/contact-ready`
- `1 = curl/contact`

Higher real hardware-style values generally mean more curl/contact.

## Confirmed Original Sim Facts

These were extracted from the installed MuJoCo environment on the Ubuntu
training PC.

```text
sim_ctrl = home_ctrl + sim_action * action_scale
home_ctrl = [0.09, 0.09, 0.09, 0.09, 0.75, 0.035, 0.1]
action_scale = [0.02, 0.02, 0.02, 0.02, 0.7, 0.003, 0.012]
```

For original sim tendon channels, positive action lengthened/opened and
negative action shortened/curled. This mismatch is why later hardware01 work
uses real-order `u in [0, 1]` instead of the original sim delta-action language.

## Safe Hardware Script Behavior

Hardware-moving scripts dry-run unless `--run` is present. The main entry points
are:

- `scripts/replay_hardware01_u_trace_safe.py`: safest exact `u_real_order`
  replay tool.
- `scripts/channel_friction_sweep.py`: one-channel or multi-channel no-cube
  current/range sweep.
- `scripts/live_policy_control.py`: live closed-loop actor runner with telemetry
  and safety limits.

Default safety aborts:

```text
current: 4000 mA
temperature: 65 C
```

Real-hand tests should log commands, positions, currents, temperatures, and
abort reasons to `logs/`.

## Current Fitted Replay Preset

Named preset:

```bash
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --preset physics_id_rollout0_real_hand_fitted
```

Source trace:

```text
sim/hardware01_real_calibrated_physics_id_trace_20260708/hardware01_physics_id_rollout0_u_trace.json
```

Fitted replay transform:

```text
channel_scale = thumb_abd=0.90,thumb_flex=0.5,thumb_tendon=0.6,index=0.50,middle=0.7
channel_bias = thumb_abd=-0.04,thumb_flex=-0.32,thumb_tendon=-0.14,index=0.34,middle=0.12,pinky=0.04
```

Dry-run command ranges:

```text
thumb_abd: 0.326-0.864
thumb_flex: 0.105-0.319
thumb_tendon: 0.241-0.478
index: 0.681-0.961
middle: 0.304-0.718
ring: 0.370-0.772
pinky: 0.445-0.826
```

This is an open-loop fitted replay baseline, not a trained closed-loop actor.

## Calibration And Replay Notes

`aero_hand_calibration.json` stores the current Mac-side raw rest/open
calibration. It helps reduce command/position mismatch, but it does not solve
all idle current or mechanical preload issues.

For newer `RealCalibrated` traces, do not add old replay-time scale/bias unless
intentionally doing a diagnostic override. Those calibration values were built
into the training environment.

Exact sim `u_real_order` traces are exported and replayed on the real hand to
separate policy quality from live observation/control bugs.

## Actor Observation Constraint

Actors intended for real deployment should use deployable hand signals:

- hardware position proxy
- current/force proxy
- last action

The critic may use privileged sim state during training. Actor policies should
not require cube pose, orientation, or velocity unless a real cube-sensing path
is added.

## Local Fixes

`launch_gui.sh` runs `scripts/patch_aero_gui_macos.py` before launching the GUI
because Tk's `-zoomed` window attribute is not supported on macOS.

`scripts/aero_hand_control.py` centralizes serial commands/readbacks, rest
recovery, telemetry reads, and retry behavior used by the safer scripts.

## Training Source

The active Ubuntu training source is outside this git repository:

```text
hw@192.168.9.63:/home/hw/aero-hand-sim
```

That source tree is not git-controlled. Before editing remote simulation source,
create a timestamped backup and copy important patches/artifacts back into this
repository under `sim/`.

## 45 mm Ball Training Variant

The first ball-training env is:

```text
AeroBall45mmRotateZAxisHardware01RealTunedWindow
```

It uses a `0.0225 m` radius sphere, equivalent to a `4.5 cm` diameter ball. The
MuJoCo body/freejoint/geom/sensor names intentionally remain `cube` internally
so existing reward, randomization, trace, and export code can be reused.

The first copied videos were visually misleading: the real physical sphere was
present, but the visible render mostly showed the tiny black orientation marker.
The corrected XML keeps the physical sphere unchanged and adds a non-colliding
orange visual sphere in render group `2`. Use the visual-fix videos for review:

```text
sim/ball45_real_tuned_window_visualfix_20260710/
```

Remote source snapshot:

```text
sim/ball45_real_tuned_window_remote_source_20260710/
```
