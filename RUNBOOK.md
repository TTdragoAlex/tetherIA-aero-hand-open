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
