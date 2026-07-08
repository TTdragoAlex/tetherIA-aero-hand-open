# RUNBOOK.md

## Hardware Assumptions
- Real hand is connected to Mac by USB serial only when explicitly testing.
- Hand must be mounted and clear before any `--run` command.
- Disconnect hand when not needed if servo noise is uncomfortable.
- Safety defaults: current abort `4000 mA`, temperature abort `60 C`.
- Real command order: `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`.

## Mac Setup From Scratch
```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python --version
./.venv/bin/python scripts/list_ports.py
```

If the GUI is needed:
```bash
cd "/Users/alextang/Documents/Robot Hand"
./launch_gui.sh
```

Firmware compile check:
```bash
cd "/Users/alextang/Documents/Robot Hand/firmware-platformio"
../.venv/bin/platformio run
```

## Ubuntu Training PC Setup
```bash
ssh hw@192.168.9.63
# enter the operator-provided password when prompted
cd /home/hw/aero-hand-sim
source .venv/bin/activate
```

Check current calibrated run:
```bash
cd /home/hw/aero-hand-sim
cat runs/nohup_logs/latest_hardware01_real_calibrated_run.txt
ps -p 82740 -o pid,etime,pcpu,pmem,cmd
tail -120 runs/nohup_logs/aero_hardware01_real_calibrated_fresh_20260707_093702.log
```

Check current smooth calibrated run:
```bash
cd /home/hw/aero-hand-sim
cat runs/nohup_logs/latest_hardware01_real_calibrated_smooth_run.txt
ps -p 87482 -o pid,etime,pcpu,pmem,cmd
tail -120 runs/nohup_logs/aero_hardware01_real_calibrated_smooth_fresh_20260707_104654.log
```

Check current anti-trap calibrated run:
```bash
cd /home/hw/aero-hand-sim
cat runs/nohup_logs/latest_hardware01_real_calibrated_antitrap_run.txt
ps -p 92318 -o pid,etime,pcpu,pmem,cmd
tail -120 runs/nohup_logs/aero_hardware01_real_calibrated_antitrap_fresh_20260707_151203.log
```

Check current physics-ID calibrated run:
```bash
cd /home/hw/aero-hand-sim
cat runs/nohup_logs/latest_hardware01_real_calibrated_physics_id_run.txt
ps -p 107128 -o pid,etime,pcpu,pmem,cmd
tail -120 runs/nohup_logs/aero_hardware01_real_calibrated_physics_id_fresh_20260708_104812.log
```

## Start A New Training Run
Only do this if the current run is finished or intentionally stopped.
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
echo $!
```

For the smoother variant, use:

```bash
cd /home/hw/aero-hand-sim
RUN_ID=aero_hardware01_real_calibrated_smooth_fresh_$(date +%Y%m%d_%H%M%S)
LOG=/home/hw/aero-hand-sim/runs/nohup_logs/${RUN_ID}.log
echo "$RUN_ID" > /home/hw/aero-hand-sim/runs/nohup_logs/latest_hardware01_real_calibrated_smooth_run.txt
nohup env MUJOCO_GL=egl /home/hw/aero-hand-sim/.venv/bin/python mujoco_playground/learning/train_jax_ppo.py \
  --env_name=AeroCubeRotateZAxisHardware01RealCalibratedSmooth \
  --domain_randomization \
  --num_timesteps=150000000 \
  --num_evals=25 \
  --num_videos=3 \
  --suffix=${RUN_ID} \
  --use_tb > "$LOG" 2>&1 &
echo $!
```

For the anti-trap variant, use:

```bash
cd /home/hw/aero-hand-sim
RUN_ID=aero_hardware01_real_calibrated_antitrap_fresh_$(date +%Y%m%d_%H%M%S)
LOG=/home/hw/aero-hand-sim/runs/nohup_logs/${RUN_ID}.log
echo "$RUN_ID" > /home/hw/aero-hand-sim/runs/nohup_logs/latest_hardware01_real_calibrated_antitrap_run.txt
nohup env MUJOCO_GL=egl /home/hw/aero-hand-sim/.venv/bin/python mujoco_playground/learning/train_jax_ppo.py \
  --env_name=AeroCubeRotateZAxisHardware01RealCalibratedAntiTrap \
  --num_timesteps=150000000 \
  --num_evals=25 \
  --reward_scaling=1.0 \
  --num_videos=3 \
  --suffix=${RUN_ID} > "$LOG" 2>&1 &
echo $!
```

For the physics-ID variant, use:

```bash
cd /home/hw/aero-hand-sim
RUN_ID=aero_hardware01_real_calibrated_physics_id_fresh_$(date +%Y%m%d_%H%M%S)
LOG=/home/hw/aero-hand-sim/runs/nohup_logs/${RUN_ID}.log
echo "$RUN_ID" > /home/hw/aero-hand-sim/runs/nohup_logs/latest_hardware01_real_calibrated_physics_id_run.txt
nohup env MUJOCO_GL=egl XLA_PYTHON_CLIENT_PREALLOCATE=false /home/hw/aero-hand-sim/.venv/bin/python mujoco_playground/learning/train_jax_ppo.py \
  --env_name=AeroCubeRotateZAxisHardware01RealCalibratedPhysicsID \
  --domain_randomization \
  --num_timesteps=150000000 \
  --num_evals=25 \
  --reward_scaling=1.0 \
  --num_videos=3 \
  --suffix=${RUN_ID} > "$LOG" 2>&1 &
echo $!
```

## Real-Hand No-Cube Current Sweep
Use when checking springs/friction before policy tests.
```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python scripts/channel_friction_sweep.py \
  --run \
  --channels index,middle,ring,pinky \
  --start 0.0 \
  --stop 0.90 \
  --step 0.05 \
  --hold 0.35 \
  --max-step-delta 0.02
```

## Exact Trace Replay On Real Hand
Start no-cube, mounted and clear:
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

For new `RealCalibrated` traces, try no extra channel scale/bias first because calibration is trained into the env/export.

If a diagnostic override is needed, record clearly that it is an override and do
not feed that result back as if it were the base policy behavior.

## Live Policy Control
Use only after exact trace replay looks safe/plausible.
```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python scripts/live_policy_control.py \
  --run \
  --steps 220 \
  --rate 12 \
  --playback-scale 1.0 \
  --position-gain 1.0 \
  --thumb-abd-gain 1.0 \
  --current-scale-ma 4000 \
  --use-signed-current \
  --sample-every 5
```

Point `--policy` or equivalent script option to the latest exported actor if the script does not default to it.

## Debugging Common Issues
- `Permission denied` over one-shot SSH: use interactive `ssh hw@192.168.9.63` and enter the operator-provided password.
- Training log empty at start: often normal during JAX/XLA compile; check `ps` and run dir creation.
- Current abort at startup: inspect CSV for channel; commonly thumb_flex/ring/pinky spikes, sometimes from posture/cube preload.
- Invalid serial response frame: retry; safe scripts send raw rest during recovery.
- Real motion weaker than sim: compare exact trace video and real replay before changing policy code.
- Cube not rotating but hand touches cube: likely contact/training mismatch; do not solve only with manual channel bias unless doing diagnostics.
- New `RealCalibrated` policy still weak: first compare exact sim trace vs real no-cube replay; if commands match but cube does not rotate, inspect contact/friction/reward before changing serial mapping.
- Sim midpoint looks unlike real midpoint: this is known; prefer broader action-to-joint randomization or calibrated training over one-off midpoint hacks.

## Copying Artifacts Back To Mac
From Mac, use `scp` with quoted remote paths when wildcards are involved:
```bash
mkdir -p "/Users/alextang/Documents/Robot Hand/sim/hardware01_real_calibrated_YYYYMMDD"
scp 'hw@192.168.9.63:/home/hw/aero-hand-sim/logs/<RUN_DIR>/rollout*.mp4' \
  "/Users/alextang/Documents/Robot Hand/sim/hardware01_real_calibrated_YYYYMMDD/"
```
If zsh says `no matches found`, quote the remote path as shown.

Latest copied `RealCalibrated` videos:

```text
sim/hardware01_real_calibrated_20260707/rollout0.mp4
sim/hardware01_real_calibrated_20260707/rollout1.mp4
sim/hardware01_real_calibrated_20260707/rollout2.mp4
```

The first `RealCalibrated` videos were judged too jittery for hardware replay.
The `RealCalibratedSmooth` videos were smoother, but rollout 1 and rollout 2
showed thumb-index trapping. Wait for anti-trap rollout videos before
exporting/replaying a trace.

The anti-trap real replay was electrically safe but visually failed: the thumb
pushed the cube laterally off the hand. Use the physics-ID variant before any
new live-policy attempt.

Latest copied `PhysicsID` artifacts:

```text
sim/hardware01_real_calibrated_physics_id_20260708/rollout0.mp4
sim/hardware01_real_calibrated_physics_id_20260708/rollout1.mp4
sim/hardware01_real_calibrated_physics_id_20260708/rollout2.mp4
sim/hardware01_real_calibrated_physics_id_20260708/config.json
sim/hardware01_real_calibrated_physics_id_20260708/aero_hardware01_real_calibrated_physics_id_fresh_20260708_104812.log
```

The `PhysicsID` training run completed cleanly. Final checkpoint is
`000157286400`, final logged reward is `11.216`, and best logged reward observed
was `11.654` at `144179200`. Initial visual review of rollouts 0, 1, and 2 shows
the cube staying seated and rotating without obvious thumb-side ejection in sim.
Next step is to export an exact smoothed `u_real_order` trace, dry-run
`scripts/replay_hardware01_u_trace_safe.py` without old channel scale/bias, then
decide whether a no-cube hardware replay is worth doing.

PhysicsID rollout 0 exact replay was tested on hardware and stayed electrically
safe, but visually failed: the thumb still pushed the cube off the hand. Do not
move to live actor export from this checkpoint.

If doing one more hardware diagnostic before retraining, use a deliberately
thumb-attenuated override on rollout 0. This is not a valid base-policy replay;
it is only a diagnostic for whether thumb lateral authority is the main failure:

```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --run \
  --trace sim/hardware01_real_calibrated_physics_id_trace_20260708/hardware01_physics_id_rollout0_u_trace.json \
  --steps 120 \
  --playback-scale 1.00 \
  --channel-scale thumb_abd=0.50,thumb_flex=0.85,thumb_tendon=0.85 \
  --channel-bias thumb_abd=-0.05 \
  --max-step-delta 0.08 \
  --sample-every 5
```

This changes rollout 0 approximately to thumb_abd `0.376-0.675`, thumb_flex
`0.372-0.737`, and thumb_tendon `0.332-0.667`, while leaving fingers unchanged.
If this keeps the cube seated, train the next env with explicit thumb-abduction
range/penalty constraints. If it still ejects, prioritize thumb/palm contact
geometry and opposing support in sim.

Best operator-tuned PhysicsID rollout 0 replay so far:

```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --run \
  --trace sim/hardware01_real_calibrated_physics_id_trace_20260708/hardware01_physics_id_rollout0_u_trace.json \
  --steps 120 \
  --playback-scale 1.00 \
  --channel-scale thumb_abd=0.90,thumb_flex=0.5,thumb_tendon=0.6,index=0.50 \
  --channel-bias thumb_abd=-0.02,thumb_flex=-0.32,thumb_tendon=-0.14,index=0.3 \
  --max-step-delta 0.08 \
  --sample-every 5
```

Dry-run range for this command: thumb_abd `0.346-0.884`, thumb_flex
`0.105-0.319`, thumb_tendon `0.241-0.478`, index `0.641-0.921`, middle
`0.115-0.640`, ring `0.370-0.772`, pinky `0.405-0.786`. The operator reported
this as mostly working. Treat it as evidence for the next training command
window: very low thumb flex/tendon, broad thumb abduction, high index support,
and unchanged middle support.

For a roughly one-minute replay, repeat the same trace 10 times without resting
between loops:

```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --run \
  --trace sim/hardware01_real_calibrated_physics_id_trace_20260708/hardware01_physics_id_rollout0_u_trace.json \
  --playback-scale 1.00 \
  --channel-scale thumb_abd=0.90,thumb_flex=0.5,thumb_tendon=0.6,index=0.50 \
  --channel-bias thumb_abd=-0.02,thumb_flex=-0.32,thumb_tendon=-0.14,index=0.3 \
  --max-step-delta 0.08 \
  --sample-every 5 \
  --repeat 10
```

At 20 Hz, the 125-step trace lasts about 6.25 seconds, so `--repeat 10` lasts
about 62.5 seconds.
