# PROJECT_STATE.md

## Current Goal
Train and transfer an Aero/TetherIA robot hand cube-rotation policy that works on the real hand, not only in simulation. The immediate goal is to train a real-calibrated anti-trap policy that keeps the smoother motion gains while avoiding thumb-index pinching that wedges the cube between the fingers.

## Current Working State
- Mac project root: `/Users/alextang/Documents/Robot Hand`.
- Training PC: `hw@192.168.9.63:/home/hw/aero-hand-sim`.
- Physical hand works: all servos can move, homing/calibration is usable, and GUI sliders operate the hand.
- Current physical issue: policies can touch/move the cube, but produce little reliable cube rotation. The real hand often cages/pushes instead of rolling the cube as the sim video does.
- Current hypothesis: the transfer layer is mostly functional now; remaining gap is sim environment/contact/training mismatch, especially thumb/finger posture, contact geometry, and overly fast simulated action strategies.
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
- New smoother remote training env implemented on Ubuntu PC: `AeroCubeRotateZAxisHardware01RealCalibratedSmooth`.
- Confirmed original sim action facts: `sim_ctrl = home_ctrl + sim_action * action_scale`, `home_ctrl=[0.09,0.09,0.09,0.09,0.75,0.035,0.1]`, `action_scale=[0.02,0.02,0.02,0.02,0.7,0.003,0.012]`.
- Real-calibrated training uses real-order scale `[0.21,0.21,0.315,1.35,1.35,1.25,1.20]` and bias `[-0.12,-0.22,-0.18,0,0,0,0]`.
- Smooth variant changes include `action_repeat=2`, `action_smoothing_max_delta=0.035`, stronger action/thumb rate and accel penalties, and `linvel=-0.18`.
- New anti-trap remote training env implemented on Ubuntu PC: `AeroCubeRotateZAxisHardware01RealCalibratedAntiTrap`.
- Anti-trap variant inherits the smooth settings and adds low-rotation penalties for thumb/index geometric trapping and thumb/index pinch commands.
- Exact anti-trap `u_real_order` traces exported from checkpoint `000157286400` under `sim/hardware01_real_calibrated_antitrap_trace_20260707/`.
- Anti-trap rollout 1 exact trace replay completed on hardware with no cube and with cube on 2026-07-08; both runs stayed below safety abort limits.

## Partially Working
- Exact sim `u_real_order` traces can be replayed on the real hand.
- Closed-loop live policy can command dynamic hand motions.
- Real hand can touch and slightly move cube, but not consistently rotate it.
- Best recent exact-trace real replay used calibrated channel scaling/bias and looked closer, but still did not produce reliable rotation.

## Broken Or Uncertain
- Sim videos show useful rolling torque; real hand with same/similar commands mostly cages or pushes.
- Middle/index/ring motion in reality has often been weaker than sim, depending on mapping and scale.
- Thumb involvement remains sensitive: too much thumb curl clamps into the palm; too little thumb abduction misses the cube.
- The completed `RealCalibrated` rollout videos looked too jittery: cube rotation came with bouncing, trapped-object impacts, and frequent thumb motion. Do not replay this policy on the real hand.
- The completed `RealCalibratedSmooth` rollout videos looked much smoother, but rollout 1 and rollout 2 often rotate the cube while it is wedged between thumb and index. Do not replay this policy on the real hand until an anti-trap variant is reviewed.
- It is unknown whether the new calibration/randomization fixes the midrange joint-coupling mismatch or only makes sim videos look better. This must be checked by exact trace replay before live policy testing.

## Important Files
- `scripts/aero_hand_control.py`: serial protocol wrapper for real hand commands/readbacks.
- `scripts/replay_hardware01_u_trace_safe.py`: safest current open-loop exact trace replay for hardware01 `u_real_order` JSON traces.
- `scripts/live_policy_control.py`: closed-loop actor runner using real GET_POS/GET_CURR style observations.
- `scripts/channel_friction_sweep.py`: per-servo no-cube current/range sweep.
- `scripts/audit_sim_to_real_mapping.py`: mapping correctness audit.
- `sim/hardware01_exact_rollout_trace_20260706/`: exact sim rollout videos and `u_real_order` traces for replay/compare.
- `sim/hardware01_real_calibrated_20260707/`: copied videos from the completed `RealCalibrated` run.
- `sim/hardware01_real_calibrated_antitrap_trace_20260707/`: exact anti-trap rollout traces exported after env smoothing in physical command order.
- `sim/live_actor_export_hardware01_efficient_000157286400/`: current efficient actor export.
- Remote `rotate_z.py`: `/home/hw/aero-hand-sim/mujoco_playground/mujoco_playground/_src/manipulation/aero_hand/rotate_z.py`.
- Remote registry: `/home/hw/aero-hand-sim/mujoco_playground/mujoco_playground/_src/manipulation/__init__.py`.
- Remote PPO config: `/home/hw/aero-hand-sim/mujoco_playground/mujoco_playground/config/manipulation_params.py`.
- Remote source backups before smooth variant edit: `/home/hw/aero-hand-sim/backups/20260707_104223/`.
- Remote source backups before anti-trap variant edit: `/home/hw/aero-hand-sim/backups/20260707_150838_anti_trap/`.

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

Smooth training run started:
- PID: `87482`
- Run id: `aero_hardware01_real_calibrated_smooth_fresh_20260707_104654`
- Log: `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_calibrated_smooth_fresh_20260707_104654.log`
- Run dir: `/home/hw/aero-hand-sim/logs/AeroCubeRotateZAxisHardware01RealCalibratedSmooth-20260707-104656-aero_hardware01_real_calibrated_smooth_fresh_20260707_104654`
- Smoke test passed before launch: env loaded, `action_mode=hardware_01_real_order_real_calibrated_smooth`, `action_repeat=2`, `action_smoothing_max_delta=0.035`, actor obs shape `(21,)`.

Anti-trap training run started:
- PID: `92318`
- Run id: `aero_hardware01_real_calibrated_antitrap_fresh_20260707_151203`
- Log: `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_calibrated_antitrap_fresh_20260707_151203.log`
- Latest-run pointer: `/home/hw/aero-hand-sim/runs/nohup_logs/latest_hardware01_real_calibrated_antitrap_run.txt`
- Env: `AeroCubeRotateZAxisHardware01RealCalibratedAntiTrap`
- Smoke test passed before launch: env loaded, `action_mode=hardware_01_real_order_real_calibrated_anti_trap`, `action_repeat=2`, `action_smoothing_max_delta=0.035`, actor obs shape `(21,)`, finite reward, active `reward/thumb_index_trap` metric.

Anti-trap training run completed:
- Final checkpoint: `000157286400`
- Final logged reward: `15.875`
- Best logged reward observed: `16.023` at `124518400`
- Training completed, but automatic post-training render failed because OpenGL was not initialized in that process.
- Videos were regenerated with `MUJOCO_GL=egl` using play-only restore from final checkpoint.
- Render run dir: `/home/hw/aero-hand-sim/logs/AeroCubeRotateZAxisHardware01RealCalibratedAntiTrap-20260707-154512-aero_hardware01_real_calibrated_antitrap_render_20260707_154510`
- Copied local videos:
  - `sim/hardware01_real_calibrated_antitrap_20260707/rollout0.mp4`
  - `sim/hardware01_real_calibrated_antitrap_20260707/rollout1.mp4`
  - `sim/hardware01_real_calibrated_antitrap_20260707/rollout2.mp4`
- Video review: less obvious thumb-index wedging than the smooth run, especially rollout 1, but still a cradle/pocket rolling strategy rather than a clean free roll. Do not move directly to hardware replay without deliberate review.

Anti-trap exact trace export and hardware replay:
- Source env: `AeroCubeRotateZAxisHardware01RealCalibratedAntiTrap`
- Source checkpoint: `000157286400`
- Selected trace: `sim/hardware01_real_calibrated_antitrap_trace_20260707/hardware01_antitrap_rollout1_u_trace.json`
- Trace field: `u_real_order`, exported from `next_state.info["last_act"]` after hardware01 mapping and smoothing clamp, not raw policy output.
- Physical command order: `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`
- Replay-time scale/bias: none.
- Dry-run passed with max trace delta `0.070`, under replay cap `0.08`.
- No-cube replay log: `logs/hardware01_u_trace_replay_20260708_093016.csv`
  - Rows: `125`
  - Max sampled absolute current: `1436.5 mA`
  - Max sampled temperature: `35 C`
  - Max sampled target/position error: `0.052`
  - No abort.
- Cube replay log: `logs/hardware01_u_trace_replay_20260708_093326.csv`
  - Rows: `125`
  - Max sampled absolute current: `1436.5 mA`
  - Max sampled temperature: `36 C`
  - Max sampled target/position error: `0.048`
  - No abort.
- Visual review from `/Users/alextang/Downloads/IMG_5309.mov`: cube moves slightly, but the thumb acts as a lateral ejector and pushes the cube off the hand. This is not a live-policy candidate.
- Next direction: start physics-identification / sim-real contact investigation before more reward-only policy training. The key mismatch appears to be thumb/finger contact geometry and support, not telemetry safety or command delivery.

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
