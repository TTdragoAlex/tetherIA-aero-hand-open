# TetherIA Aero Hand Open

This repository tracks Mac-side control, firmware notes, sim artifacts, and
sim-to-real transfer experiments for a TetherIA/Aero robot hand.

Official TetherIA product and SDK documentation lives at:

https://docs.tetheria.ai/docs

Use the official docs for vendor setup, SDK expectations, firmware context, and
hardware-specific reference material. This repository documents the local
integration work, safety wrappers, calibration findings, policy-transfer
experiments, and current unresolved problems.

## Safety First

Do not move the physical hand unless it is connected, mounted, and clear.

Movement commands in this repo normally require `--run`; without it they should
dry-run. Keep the default safety aborts unless explicitly testing the safety
system itself:

- Current abort: `4000 mA`
- Temperature abort: `60 C`
- Physical command order: `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`

Real-hand tests should log commands, positions, currents, temperatures, and
abort reasons. Disconnect the hand when it is no longer needed.

## Project Goal

The goal is to train and transfer a cube-rotation policy that works on the real
hand, not only in MuJoCo simulation.

The physical hand is functional: servos move, homing/calibration works, the GUI
can operate sliders, and exact sim command traces can be replayed. The main
remaining issue is sim-to-real transfer. Current policies can touch and move the
cube, but the real hand usually cages or pushes it instead of producing the
rolling torque seen in sim videos.

Current hypothesis: the transfer layer is mostly working; the larger mismatch is
in sim environment assumptions, contact geometry, thumb/finger posture, and
training rewards.

## Repository Layout

- `scripts/`: Mac-side control, telemetry, replay, live-policy, current
  profiling, mapping audits, and helper tools.
- `sim/`: Copied training videos, actor exports, exact policy traces, and sim
  diagnostics.
- `logs/`: CSV logs from real-hand tests, replay runs, live-policy runs, current
  sweeps, and mapping audits.
- `firmware-platformio/`: ESP32/PlatformIO firmware project for the hand
  controller.
- `firmware-bin/`: Firmware binary copied from the vendor workflow.
- `upstream/`: Copied upstream/vendor examples kept for reference.
- `aero_hand_calibration.json`: Current Mac-side raw rest/open calibration.
- `PROJECT_STATE.md`, `DECISIONS.md`, `TODO.md`, `RUNBOOK.md`: Current handoff,
  decisions, next tasks, and operator commands.

The Ubuntu training PC source lives outside this repository:

```bash
hw@192.168.9.63:/home/hw/aero-hand-sim
```

That remote source is not git-controlled, so create timestamped backups before
editing it.

## Local Setup

Python virtual environment:

```bash
./.venv/bin/python
```

List serial ports:

```bash
./.venv/bin/python scripts/list_ports.py
```

Open the GUI:

```bash
./launch_gui.sh
```

Compile firmware:

```bash
cd firmware-platformio
../.venv/bin/platformio run
```

## Important Local Fixes And Changes

### macOS SDK/GUI Compatibility

The TetherIA Python GUI needed a macOS patch because Tk's `-zoomed` window
attribute is not supported on macOS. `launch_gui.sh` runs
`scripts/patch_aero_gui_macos.py` before launching the GUI.

### Raw Rest Calibration

The hand can draw high idle current when command targets do not match the
physical rest pose. `aero_hand_calibration.json` stores a raw actuator rest pose,
and `scripts/aero_hand_control.py` centralizes loading it, sending rest, reading
telemetry, and retrying serial reads.

Calibration improved command/position mismatch, but it did not remove every idle
current source. Channel 1 has previously stayed around `250-270 mA` even near
its measured lower-position rest, suggesting mechanical preload, stop contact,
tendon tension, or trim/homing offset rather than a GUI math error.

### Safer Hardware Scripts

Hardware-moving tools default to dry-run mode and require `--run`. The main safe
entry points are:

- `scripts/channel_friction_sweep.py`: one-channel no-cube current/range sweep.
- `scripts/replay_hardware01_u_trace_safe.py`: safest current exact `u_real_order`
  trace replay.
- `scripts/live_policy_control.py`: live closed-loop actor runner with telemetry
  and safety limits.

Safe scripts send rest during recovery when possible and log telemetry to
`logs/`.

### Real-Order Policy Semantics

Deployment-facing policies now use real hardware order:

```text
[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]
```

The old sim-facing order:

```text
[index, middle, ring, pinky, thumb_abd, thumb_flex, thumb_tendon]
```

caused repeated mapping/sign confusion, so new hardware01 policies use real
order with `u in [0, 1]`, where higher generally means more curl/contact.

### Actor Observation Constraint

Actors intended for real deployment use deployable hand signals: hardware
position proxy, current/force proxy, and last action. The critic may still use
privileged sim state during training. Actor policies should not require cube
pose/orientation/velocity unless a real cube-sensing path is added.

### Exact Trace Debugging

Exact sim `u_real_order` traces are exported and replayed on the real hand to
separate policy quality from live observation/control bugs. Current exact traces
live under:

```text
sim/hardware01_exact_rollout_trace_20260706/
```

The best recent old-policy replay required compressed thumb ranges and expanded
finger ranges, which motivated training a real-calibrated variant instead of
continuing endless manual replay bias tweaks.

### Real-Calibrated Training Variant

The new remote environment `AeroCubeRotateZAxisHardware01RealCalibrated` maps the
actor's real-command `u` through real-tested scale/bias inside sim. It also
adds/strengthens penalties against clamping without rotation:

- stalled-force penalty
- non-thumb-force penalty
- static-clamp penalty
- thumb-overcurl penalty

The intent is to teach the policy inside a command/contact window that better
matches the real hand.

## Current State

Working:

- Physical hand moves and can be controlled from GUI/scripts.
- Homing/calibration is usable.
- Exact sim traces can be replayed on real hardware.
- Closed-loop live actor control can command dynamic motions.
- Mapping/audit tools and telemetry logging exist.

Partially working:

- Real hand can contact and slightly move the cube.
- Best exact-trace replay looked closer with calibrated channel scale/bias.
- Old efficient actor exports and exact traces are preserved as baselines.

Not solved:

- Real cube rotation is not reliable.
- Real execution often cages/clamps/pushes the cube instead of rolling it.
- Thumb posture is sensitive: too much curl clamps into the palm; too little
  abduction misses the cube.
- Finger strength/contact differs from sim depending on mapping and scale.
- The new `RealCalibrated` training run still needs evaluation.

## Current Best Baseline Artifacts

- Actor export:
  `sim/live_actor_export_hardware01_efficient_000157286400/actor_policy.npz`
- Sim video:
  `sim/hardware01_efficient_continue_20260706/rollout0.mp4`
- Exact trace:
  `sim/hardware01_exact_rollout_trace_20260706/hardware01_rollout0_u_trace.json`

Best recent old-policy replay command:

```bash
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --run \
  --trace sim/hardware01_exact_rollout_trace_20260706/hardware01_rollout0_u_trace.json \
  --steps 120 \
  --playback-scale 1.00 \
  --channel-scale thumb_abd=0.21,thumb_flex=0.21,thumb_tendon=0.315,index=1.35,middle=1.35,ring=1.25,pinky=1.20 \
  --channel-bias thumb_abd=-0.12,thumb_flex=-0.22,thumb_tendon=-0.18 \
  --max-step-delta 0.08 \
  --sample-every 5
```

For new `RealCalibrated` traces, try no extra channel scale/bias first because
the calibration is trained into the environment/export.

## Remote Training Run

Latest documented remote run:

- Environment: `AeroCubeRotateZAxisHardware01RealCalibrated`
- PID: `82740`
- Run id: `aero_hardware01_real_calibrated_fresh_20260707_093702`
- Log:
  `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_calibrated_fresh_20260707_093702.log`
- Run directory:
  `/home/hw/aero-hand-sim/logs/AeroCubeRotateZAxisHardware01RealCalibrated-20260707-093704-aero_hardware01_real_calibrated_fresh_20260707_093702`

Check it from the training PC:

```bash
cd /home/hw/aero-hand-sim
ps -p 82740 -o pid,etime,pcpu,pmem,cmd
tail -120 runs/nohup_logs/aero_hardware01_real_calibrated_fresh_20260707_093702.log
find logs/AeroCubeRotateZAxisHardware01RealCalibrated-20260707-093704-aero_hardware01_real_calibrated_fresh_20260707_093702 -maxdepth 2 -type f | sort | tail -50
```

## Next Safest Tasks

1. Monitor the `RealCalibrated` training run.
2. Copy new rollout videos to `sim/hardware01_real_calibrated_YYYYMMDD/`.
3. Inspect sim motion before touching hardware.
4. Export the best actor and exact `u_real_order` trace.
5. Replay the trace on the real mounted hand with no cube.
6. Replay with cube only after no-cube replay is safe and plausible.
7. Run live closed-loop control only after exact trace replay looks good.

## Git Notes

This repository was initialized from an existing working directory and pushed to:

https://github.com/TTdragoAlex/tetherIA-aero-hand-open

The first commit is a baseline snapshot of docs, scripts, logs, firmware source,
firmware binary, and copied sim artifacts. Generated PlatformIO build output is
ignored via:

```text
firmware-platformio/.pio/
```

