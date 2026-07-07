# PROJECT_STATE.md

## Current Goal
Train and transfer an Aero/TetherIA robot hand cube-rotation policy that works on the real hand, not only in simulation. The immediate goal is to make training match the real hand better by using real-tested command ranges, stronger contact randomization, and penalties against clamping without rotation.

## Current Working State
- Mac project root: `/Users/alextang/Documents/Robot Hand`.
- Training PC: `hw@192.168.9.63:/home/hw/aero-hand-sim`.
- Physical hand works: all servos can move, homing/calibration is usable, and GUI sliders operate the hand.
- Current physical issue: policies can touch/move the cube, but produce little reliable cube rotation. The real hand often cages/pushes instead of rolling the cube as the sim video does.
- Current hypothesis: the transfer layer is mostly functional now; remaining gap is sim environment/contact/training mismatch, especially thumb/finger posture and contact geometry.
- Cube size is not the active suspected bottleneck; smaller/larger cubes were tried and the current cube is considered the best available physical choice.
- Sim endpoints `u=0` and `u=1` are visually acceptable, but midrange `u=0.5` differs: real fingers bend across joints while sim bends mostly at knuckles.

## Implemented
- Mac-side hand SDK/control helpers in `scripts/aero_hand_control.py`.
- Safe policy replay scripts:
  - `scripts/replay_policy_trace_safe.py`
  - `scripts/replay_hardware01_u_trace_safe.py`
- Live closed-loop actor runner: `scripts/live_policy_control.py`.
- Mapping/audit tools:
  - `scripts/audit_sim_to_real_mapping.py`
  - `scripts/run_mapping_tournament.py`
  - `scripts/channel_friction_sweep.py`
- Hardware01 sim action diagnostics copied under `sim/hardware01_action_diagnostics/`.
- Real-calibrated rollout videos copied under `sim/hardware01_real_calibrated_20260707/`.
- Current best transferred baseline artifacts:
  - `sim/live_actor_export_hardware01_efficient_000157286400/actor_policy.npz`
  - `sim/hardware01_efficient_continue_20260706/rollout0.mp4`
  - `sim/hardware01_exact_rollout_trace_20260706/hardware01_rollout0_u_trace.json`
- New remote training env implemented on Ubuntu PC: `AeroCubeRotateZAxisHardware01RealCalibrated`.
- Confirmed original sim action facts: `sim_ctrl = home_ctrl + sim_action * action_scale`, `home_ctrl=[0.09,0.09,0.09,0.09,0.75,0.035,0.1]`, `action_scale=[0.02,0.02,0.02,0.02,0.7,0.003,0.012]`.
- Real-calibrated training uses real-order scale `[0.21,0.21,0.315,1.35,1.35,1.25,1.20]` and bias `[-0.12,-0.22,-0.18,0,0,0,0]`.

## Partially Working
- Exact sim `u_real_order` traces can be replayed on the real hand.
- Closed-loop live policy can command dynamic hand motions.
- Real hand can touch and slightly move cube, but not consistently rotate it.
- Best recent exact-trace real replay used calibrated channel scaling/bias and looked closer, but still did not produce reliable rotation.

## Broken Or Uncertain
- Sim videos show useful rolling torque; real hand with same/similar commands mostly cages or pushes.
- Middle/index/ring motion in reality has often been weaker than sim, depending on mapping and scale.
- Thumb involvement remains sensitive: too much thumb curl clamps into the palm; too little thumb abduction misses the cube.
- The new `RealCalibrated` training run completed cleanly and generated rollout videos, but the videos have not yet been visually evaluated.
- It is unknown whether the new calibration/randomization fixes the midrange joint-coupling mismatch or only makes sim videos look better. This must be checked by exact trace replay before live policy testing.

## Important Files
- `scripts/aero_hand_control.py`: serial protocol wrapper for real hand commands/readbacks.
- `scripts/replay_hardware01_u_trace_safe.py`: safest current open-loop exact trace replay for hardware01 `u_real_order` JSON traces.
- `scripts/live_policy_control.py`: closed-loop actor runner using real GET_POS/GET_CURR style observations.
- `scripts/channel_friction_sweep.py`: per-servo no-cube current/range sweep.
- `scripts/audit_sim_to_real_mapping.py`: mapping correctness audit.
- `sim/hardware01_exact_rollout_trace_20260706/`: exact sim rollout videos and `u_real_order` traces for replay/compare.
- `sim/hardware01_real_calibrated_20260707/`: copied videos from the completed `RealCalibrated` run.
- `sim/live_actor_export_hardware01_efficient_000157286400/`: current efficient actor export.
- Remote `rotate_z.py`: `/home/hw/aero-hand-sim/mujoco_playground/mujoco_playground/_src/manipulation/aero_hand/rotate_z.py`.
- Remote registry: `/home/hw/aero-hand-sim/mujoco_playground/mujoco_playground/_src/manipulation/__init__.py`.
- Remote PPO config: `/home/hw/aero-hand-sim/mujoco_playground/mujoco_playground/config/manipulation_params.py`.

## Current Branch / Diff Status
- Local branch: `main`.
- Local git status currently shows this as a largely untracked working directory, not a clean committed repo.
- Important untracked top-level paths include `.gitignore`, `scripts/`, `sim/`, `logs/`, `firmware-platformio/`, `firmware-bin/`, and these handoff docs.
- Remote training PC repo is not a git repo. Backups were created before the last remote source edit with timestamp `20260707_093413`.

## Last Successful Commands
Remote smoke test for new env:
```bash
cd /home/hw/aero-hand-sim
.venv/bin/python -m py_compile \
  mujoco_playground/mujoco_playground/_src/manipulation/aero_hand/rotate_z.py \
  mujoco_playground/mujoco_playground/_src/manipulation/__init__.py \
  mujoco_playground/mujoco_playground/config/manipulation_params.py
.venv/bin/python /tmp/smoke_real_calibrated.py
```

Remote training launch:
```bash
cd /home/hw/aero-hand-sim
RUN_ID=aero_hardware01_real_calibrated_fresh_$(date +%Y%m%d_%H%M%S)
LOG=/home/hw/aero-hand-sim/runs/nohup_logs/${RUN_ID}.log
echo "$RUN_ID" > /home/hw/aero-hand-sim/runs/nohup_logs/latest_hardware01_real_calibrated_run.txt
nohup env MUJOCO_GL=egl /home/hw/aero-hand-sim/.venv/bin/python mujoco_playground/learning/train_jax_ppo.py \
  --env_name=AeroCubeRotateZAxisHardware01RealCalibrated \
  --domain_randomization \
  --num_timesteps=150000000 \
  --num_evals=25 \
  --num_videos=3 \
  --suffix=${RUN_ID} \
  --use_tb > "$LOG" 2>&1 &
```

Training run completed:
- PID: `82740`
- Run id: `aero_hardware01_real_calibrated_fresh_20260707_093702`
- Log: `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_calibrated_fresh_20260707_093702.log`
- Run dir: `/home/hw/aero-hand-sim/logs/AeroCubeRotateZAxisHardware01RealCalibrated-20260707-093704-aero_hardware01_real_calibrated_fresh_20260707_093702`
- Final checkpoint: `000157286400`
- Final logged reward: `35.862`
- Best logged reward observed: `37.066` at `137625600`
- Copied local videos:
  - `sim/hardware01_real_calibrated_20260707/rollout0.mp4`
  - `sim/hardware01_real_calibrated_20260707/rollout1.mp4`
  - `sim/hardware01_real_calibrated_20260707/rollout2.mp4`

Best recent real exact-trace replay command:
```bash
cd "/Users/alextang/Documents/Robot Hand"
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
