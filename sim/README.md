# Aero Hand Sim Artifacts

This directory contains copied MuJoCo / MuJoCo Playground videos, traces,
training logs, actor exports, and physics-identification artifacts for the Aero
Hand cube-rotation transfer work.

For the chronological map, read `../ARTIFACT_INDEX.md` first.

## Folder Naming

Folder names usually follow this pattern:

```text
<experiment_name>_<YYYYMMDD>/
```

Examples:

- `hardware01_real_calibrated_20260707/`: first real-calibrated run.
- `hardware01_real_calibrated_physics_id_20260708/`: PhysicsID run videos.
- `hardware01_real_calibrated_physics_id_trace_20260708/`: replayable traces
  exported from the PhysicsID run.

Inside a folder, `rollout0.mp4`, `rollout1.mp4`, and `rollout2.mp4` are sampled
evaluation videos from the same checkpoint. A `rollout0.mp4` in one folder is
not the same policy as `rollout0.mp4` in another folder.

Local file modification times may be later than folder dates when files were
copied from the training PC to the Mac after the run.

## Trace Semantics

Trace JSON files ending in `_u_trace.json` contain physical command targets in
the hardware order:

```text
[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]
```

For modern hardware01 traces, replay the `u_real_order` field. It is the
env-smoothed command after the policy output has been converted to real-order
`u`. Do not use raw policy actions directly on the hand.

Use:

```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py --trace <trace.json>
```

Add `--run` only after the hand is connected, mounted, and clear.

## Current Best Real-Hand Fitted Replay

The best labeled open-loop replay is available as a preset:

```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --preset physics_id_rollout0_real_hand_fitted
```

This packages:

- `sim/hardware01_real_calibrated_physics_id_trace_20260708/hardware01_physics_id_rollout0_u_trace.json`
- fitted scale/bias discovered on the real hand,
- `--max-step-delta 0.08`,
- `--sample-every 5`,
- `--repeat 5`.

It is not a trained actor; it is the current best real-hand-fitted exact trace.

## Important Folders

- `hardware01_action_diagnostics/`: channel-by-channel `u=0..1` videos used to
  confirm hardware-order semantics.
- `hardware01_exact_rollout_trace_20260706/`: older efficient-policy videos and
  exact traces that established the trace-replay workflow.
- `hardware01_real_calibrated_20260707/`: first real-calibrated run; rejected
  because it was jittery and bouncy.
- `hardware01_real_calibrated_smooth_20260707/`: smoother run; rejected because
  it often used a thumb-index pocket.
- `hardware01_real_calibrated_antitrap_20260707/`: anti-trap run; visually
  better in sim but failed real replay by thumb-side ejection.
- `hardware01_real_calibrated_physics_id_20260708/`: PhysicsID run; looked good
  in sim but still failed exact real replay.
- `hardware01_real_calibrated_physics_id_trace_20260708/`: traces from the
  PhysicsID run; source of the current fitted replay preset.
- `hardware01_real_tuned_window_20260708/`: RealTunedWindow run copied to the
  Mac on 2026-07-09; plausible in sim but still failed on the real hand.
- `hardware01_real_tuned_window_trace_20260708/`: exact traces from
  RealTunedWindow.
- `physics_id_antitrap_rollout1_native_seeded_20260708/`: seeded native MuJoCo
  replay sweep used for physics identification.
- `physics_id_remote_source_20260708/` and
  `real_tuned_window_remote_source_20260708/`: source snapshots and patches from
  the training PC, whose source tree is not git-controlled.

## Current Conclusion

The simulator can produce seated-looking cube rotations, but those policies
still fail on the real hand. Treat sim videos as hypotheses, not proof. The next
main task is to modify the sim/physics-identification setup until exact traces
that fail on the real hand also fail in sim.

## Original Setup Goal

The original setup goal was sim-only validation before connecting anything to
the physical hand:

1. Create a separate Python 3.12 sim environment.
2. Clone the MuJoCo Menagerie model and MuJoCo Playground code.
3. Verify the TetherIA Aero Hand XML loads locally.
4. Run or inspect the `AeroCubeRotateZAxis` environment.
5. Map sim tendon/action channels to the physical-hand Python API.
6. Only later, replay very conservative policy outputs on hardware with
   current/temp aborts.

## Local Mac Expectation

This Mac can be useful for:

- Loading and inspecting the MuJoCo model.
- Rendering or stepping small simulations.
- Inspecting actions and observations.
- Building the sim-to-real adapter.

Serious RL training will probably be better on an NVIDIA GPU machine or cloud
runtime because MuJoCo Playground recommends JAX/CUDA for training speed.

## Setup Sketch

From the repo root:

```bash
/opt/homebrew/bin/python3.12 -m venv sim/.venv
sim/.venv/bin/python -m pip install --upgrade pip
sim/.venv/bin/python -m pip install mujoco
git clone https://github.com/google-deepmind/mujoco_menagerie.git sim/mujoco_menagerie
git clone https://github.com/google-deepmind/mujoco_playground.git sim/mujoco_playground
```

Then smoke-test the hand XML:

```bash
sim/.venv/bin/python scripts/sim_load_aero_hand.py
```

## Hand Connection

Keep the physical hand disconnected for all sim setup and training work. It is
only needed later for carefully gated sim-to-real playback tests.
