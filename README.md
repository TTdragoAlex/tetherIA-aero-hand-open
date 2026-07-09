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

Current hypothesis: command replay is safe enough to debug, but the simulator is
not yet physically honest enough. Policies that look good in sim still fail on
the real hand, usually by trapping, caging, or pushing the cube away. The next
main work is sim-real identification: make the simulator reproduce the real
failure on exact traces before training another reward-only policy variant.

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
- `ARTIFACT_INDEX.md`: Chronological guide to copied sim videos, traces, logs,
  and which artifacts are still useful.

The Ubuntu training PC source lives outside this repository:

```bash
hw@192.168.9.63:/home/hw/aero-hand-sim
```

That remote source is not git-controlled, so create timestamped backups before
editing it.

## How To Read The Artifacts

Most simulation videos are stored under `sim/` in folders named with the
experiment and date. Dates use `YYYYMMDD`; for example,
`hardware01_real_calibrated_physics_id_20260708` is the PhysicsID run from
2026-07-08.

Inside one experiment folder, `rollout0.mp4`, `rollout1.mp4`, and `rollout2.mp4`
are separate rendered evaluation episodes from the same checkpoint. They are not
globally meaningful names; always read them together with the folder name.

For a chronological map of the important folders and what each one proved, read
`ARTIFACT_INDEX.md`.

Trace folders contain replayable `u_real_order` JSON commands in physical hand
order:

```text
[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]
```

The current best real-hand fitted replay is packaged as:

```bash
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --preset physics_id_rollout0_real_hand_fitted
```

Add `--run` only when the hand is connected, mounted, and clear.


## Confirmed Sim Action Facts

These facts were extracted from the installed MuJoCo environment on the Ubuntu
PC, not guessed from public docs:

- Original sim formula: `sim_ctrl = home_ctrl + sim_action * action_scale`.
- `home_ctrl = [0.09, 0.09, 0.09, 0.09, 0.75, 0.035, 0.1]`.
- `action_scale = [0.02, 0.02, 0.02, 0.02, 0.7, 0.003, 0.012]`.
- Original sim action order: `[index, middle, ring, pinky, thumb_abd, thumb_flex, thumb_tendon]`.
- Real hardware command order: `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`.
- For sim tendon channels, positive original sim action lengthens/opens and negative original sim action shortens/curls.
- For real hardware-style `u`, higher values are treated as more curl/contact.

This is why current transfer work uses hardware01 real-order `u in [0, 1]` rather
than the original sim delta action language.

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


Important real-tested replay calibration values:

```text
scale = [0.21, 0.21, 0.315, 1.35, 1.35, 1.25, 1.20]
bias  = [-0.12, -0.22, -0.18, 0.0, 0.0, 0.0, 0.0]
order = [thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]
```

For the new `RealCalibrated` env, these are built into training. Do not add the
same replay-time scale/bias again unless explicitly doing a diagnostic override.

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

## Physical-Hand Lessons So Far

- Original communication failure was hardware/soldering, not GUI logic. After
  fixing hardware, all servos moved and homing worked.
- Servo high-pitched noise tracked idle current; lower current generally meant
  less noise.
- Strong springs caused high current and jamming. Softer springs improved index
  and middle finger sweeps, but did not solve cube rotation by itself.
- Cube size is not considered the main issue now; smaller and larger cubes were
  tried, and the current cube is treated as the best physical candidate.
- Sim `u=0` and `u=1` endpoint diagnostics looked broadly acceptable, but
  `u=0.5` posture differs: the real hand bends multiple finger joints while sim
  tends to bend mainly at the knuckles. Action-to-joint randomization and the
  real-calibrated env are meant to make the policy robust to this mismatch.

## Current State

Working:

- Physical hand moves and can be controlled from GUI/scripts.
- Homing/calibration is usable.
- Exact sim traces can be replayed on real hardware.
- Closed-loop live actor control can command dynamic motions.
- Mapping/audit tools and telemetry logging exist.
- Anti-trap rollout 1 exact trace has been exported and safely replayed on
  hardware with no cube and with cube.
- Physics-identification tooling now exists for replaying the anti-trap exact
  trace under native MuJoCo physics variants.
- The first `PhysicsID` training run completed and its rollout videos were
  copied back to the Mac.

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
- The first `RealCalibrated` run was too jittery for hardware replay.
- The smoother follow-up still wedged the cube between thumb and index in some
  rollouts.
- The anti-trap cube replay passed telemetry safety but failed visually: the
  thumb pushed the cube laterally off the hand.
- `PhysicsID` sim videos looked better, but exact trace replay still failed on
  the real hand: the thumb pushed the cube off again. Do not export a live actor
  from this checkpoint.

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

## Latest Real-Calibrated Videos

The `AeroCubeRotateZAxisHardware01RealCalibrated` run from 2026-07-07 completed
cleanly and generated three rollout videos copied to the Mac:

```text
sim/hardware01_real_calibrated_20260707/rollout0.mp4
sim/hardware01_real_calibrated_20260707/rollout1.mp4
sim/hardware01_real_calibrated_20260707/rollout2.mp4
```

The same folder includes `config.json` with the run configuration and the
training log copied from the remote run.

Run summary:

- Run id: `aero_hardware01_real_calibrated_fresh_20260707_093702`
- Final checkpoint: `000157286400`
- Final logged reward: `35.862`
- Best logged reward observed: `37.066` at `137625600`

Inspect these videos before exporting a live actor or replaying an exact trace
on hardware.

Video review outcome: this first real-calibrated run is not a hardware replay
candidate. It rotates the cube partly through jittery finger/thumb impacts and
cube bouncing. The thumb moves too frequently for a plausible real-hand transfer.

The follow-up environment `AeroCubeRotateZAxisHardware01RealCalibratedSmooth`
adds hard `u` slew limiting, lower effective action cadence, stronger
action/thumb smoothness penalties, and a cube linear-velocity penalty. The
smooth run completed and videos were copied to:

```text
sim/hardware01_real_calibrated_smooth_20260707/rollout0.mp4
sim/hardware01_real_calibrated_smooth_20260707/rollout1.mp4
sim/hardware01_real_calibrated_smooth_20260707/rollout2.mp4
```

Review outcome: smoother and more rhythmic than `RealCalibrated`, but rollout 1
and rollout 2 often rotate the cube while it is stuck in a thumb-index pocket.
Do not replay it on hardware as-is.

The current remote run is
`AeroCubeRotateZAxisHardware01RealCalibratedAntiTrap`, which keeps the smooth
action cadence and adds penalties for thumb/index trapping and pinch commands:

- Run id: `aero_hardware01_real_calibrated_antitrap_fresh_20260707_151203`
- Log:
  `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_calibrated_antitrap_fresh_20260707_151203.log`
- Latest-run pointer:
  `/home/hw/aero-hand-sim/runs/nohup_logs/latest_hardware01_real_calibrated_antitrap_run.txt`
- Final checkpoint: `000157286400`
- Final logged reward: `15.875`
- Best logged reward observed: `16.023` at `124518400`

The automatic render after training failed because OpenGL was not initialized in
that process, so the videos were regenerated from the final checkpoint with
`MUJOCO_GL=egl` and copied to:

```text
sim/hardware01_real_calibrated_antitrap_20260707/rollout0.mp4
sim/hardware01_real_calibrated_antitrap_20260707/rollout1.mp4
sim/hardware01_real_calibrated_antitrap_20260707/rollout2.mp4
```

Review outcome: anti-trap is less visibly wedged than the smooth run, especially
rollout 1, but it still uses a shallow cradle/pocket rolling strategy. Hardware
replay should wait until this contact style is deliberately accepted.

Exact anti-trap trace export and hardware replay:

```text
sim/hardware01_real_calibrated_antitrap_trace_20260707/
```

- Source env: `AeroCubeRotateZAxisHardware01RealCalibratedAntiTrap`
- Source checkpoint: `000157286400`
- Selected trace:
  `sim/hardware01_real_calibrated_antitrap_trace_20260707/hardware01_antitrap_rollout1_u_trace.json`
- Trace field: `u_real_order` from env-smoothed `last_act`, not raw policy
  output.
- Physical command order:
  `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`
- Replay-time scale/bias: none.
- Dry-run passed with max trace delta `0.070`, under replay cap `0.08`.
- No-cube log: `logs/hardware01_u_trace_replay_20260708_093016.csv`;
  max sampled current `1436.5 mA`, max temp `35 C`, max sampled position error
  `0.052`, no abort.
- Cube log: `logs/hardware01_u_trace_replay_20260708_093326.csv`;
  max sampled current `1436.5 mA`, max temp `36 C`, max sampled position error
  `0.048`, no abort.

Visual review from `/Users/alextang/Downloads/IMG_5309.mov`: the cube moves a
little, but the thumb pushes it laterally off the hand before the fingers form a
useful opposing contact. Do not export/test the live actor from this checkpoint
as the next step. Start physics identification before more reward-only training.

Physics-identification result:

```text
sim/physics_id_antitrap_rollout1_native_seeded_20260708/
sim/physics_id_remote_source_20260708/
```

The corrected seeded sweep starts from the same environment reset path as
anti-trap rollout 1. Its strongest failure direction is thumb-dominant contact
with weak opposing finger support. Softening springs alone did not best explain
the replay failure because the soft-spring variant kept more useful z rotation.

New training env on the Ubuntu PC:

- `AeroCubeRotateZAxisHardware01RealCalibratedPhysicsID`
- Adds `reward/cube_planar_drift`.
- Uses a dedicated wider randomizer for cube/palm friction, thumb-vs-finger
  friction, tendon spring stiffness, and weak opposing finger actuation.
- Run id: `aero_hardware01_real_calibrated_physics_id_fresh_20260708_104812`
- Log:
  `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_calibrated_physics_id_fresh_20260708_104812.log`
- Final checkpoint: `000157286400`
- Final logged reward: `11.216`
- Best logged reward observed: `11.654` at `144179200`

Copied PhysicsID artifacts:

```text
sim/hardware01_real_calibrated_physics_id_20260708/rollout0.mp4
sim/hardware01_real_calibrated_physics_id_20260708/rollout1.mp4
sim/hardware01_real_calibrated_physics_id_20260708/rollout2.mp4
sim/hardware01_real_calibrated_physics_id_20260708/config.json
sim/hardware01_real_calibrated_physics_id_20260708/aero_hardware01_real_calibrated_physics_id_fresh_20260708_104812.log
```

Review outcome: rollouts 0, 1, and 2 keep the cube seated and rotating in sim
without obvious thumb-side ejection in sampled frames. This is promising, but it
did not transfer: rollout 0 exact replay was electrically safe, but the thumb
still pushed the cube off the hand. Do not test rollout 1 or 2 as direct live
candidates; the next work should either run one thumb-attenuated diagnostic or
train a new thumb-limited / anti-ejection variant.

Latest operator-tuned replay result: PhysicsID rollout 0 became the best
real-hand open-loop baseline when replayed with very low thumb flex/tendon,
raised index support, raised middle support, and a small pinky bias. This is now
packaged as the named preset `physics_id_rollout0_real_hand_fitted`:

```bash
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --preset physics_id_rollout0_real_hand_fitted
```

Preset details:

```text
channel_scale = thumb_abd=0.90, thumb_flex=0.5, thumb_tendon=0.6, index=0.50, middle=0.7
channel_bias  = thumb_abd=-0.04, thumb_flex=-0.32, thumb_tendon=-0.14, index=0.34, middle=0.12, pinky=0.04
```

Dry-run ranges: thumb_abd `0.326-0.864`, thumb_flex `0.105-0.319`,
thumb_tendon `0.241-0.478`, index `0.681-0.961`, middle `0.304-0.718`,
ring `0.370-0.772`, pinky `0.445-0.826`.

This is a fitted open-loop replay, not a trained closed-loop actor.

RealTunedWindow follow-up:

- Environment: `AeroCubeRotateZAxisHardware01RealTunedWindow`
- Run id: `aero_hardware01_real_tuned_window_fresh_20260708_165830`
- Final checkpoint: `000157286400`
- Final/best logged reward: `6.621`
- Copied videos/config/log:
  `sim/hardware01_real_tuned_window_20260708/`
- Copied exact traces:
  `sim/hardware01_real_tuned_window_trace_20260708/`
- Source snapshot:
  `sim/real_tuned_window_remote_source_20260708/`

Outcome: RealTunedWindow looked plausible in sim, but real replay still failed
with the same trapping/ejection behavior. Do not export this live actor. This is
the main evidence that the next work should be sim-real identification rather
than another sim-success reward variant.

Previous smooth run details:

- Run id: `aero_hardware01_real_calibrated_smooth_fresh_20260707_104654`
- Log:
  `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_calibrated_smooth_fresh_20260707_104654.log`
- Run dir:
  `/home/hw/aero-hand-sim/logs/AeroCubeRotateZAxisHardware01RealCalibratedSmooth-20260707-104656-aero_hardware01_real_calibrated_smooth_fresh_20260707_104654`

## Remote Training Run

Latest completed remote run:

- Environment: `AeroCubeRotateZAxisHardware01RealTunedWindow`
- Run id: `aero_hardware01_real_tuned_window_fresh_20260708_165830`
- Log:
  `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_tuned_window_fresh_20260708_165830.log`

Check it from the training PC:

```bash
cd /home/hw/aero-hand-sim
tail -120 runs/nohup_logs/aero_hardware01_real_tuned_window_fresh_20260708_165830.log
find logs/AeroCubeRotateZAxisHardware01RealTunedWindow-20260708-165832-aero_hardware01_real_tuned_window_fresh_20260708_165830 -maxdepth 1 -type f -name 'rollout*.mp4' -print
```

## Next Safest Tasks

1. Build a sim-real identification replay harness around exact traces.
2. Make the simulator reproduce the real trapping/ejection failure before more
   policy training.
3. Use `physics_id_rollout0_real_hand_fitted` as the current real-hand fitted
   open-loop baseline.
4. Only return to policy training after the modified sim ranks failed and
   manually fitted traces in the same direction as the real hand.

## Git Notes

This repository was initialized from an existing working directory and pushed to:

https://github.com/TTdragoAlex/tetherIA-aero-hand-open

The first commit is a baseline snapshot of docs, scripts, logs, firmware source,
firmware binary, and copied sim artifacts. Generated PlatformIO build output is
ignored via:

```text
firmware-platformio/.pio/
```
