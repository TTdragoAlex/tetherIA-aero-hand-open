# TODO.md

## 1. Monitor `RealCalibrated` Training
- Task: Check remote PID/log/checkpoints/videos for `AeroCubeRotateZAxisHardware01RealCalibrated`.
- Command:
```bash
ssh hw@192.168.9.63
cd /home/hw/aero-hand-sim
ps -p 82740 -o pid,etime,pcpu,pmem,cmd
tail -120 runs/nohup_logs/aero_hardware01_real_calibrated_fresh_20260707_093702.log
find logs/AeroCubeRotateZAxisHardware01RealCalibrated-20260707-093704-aero_hardware01_real_calibrated_fresh_20260707_093702 -maxdepth 2 -type f | sort | tail -50
```
- Verify: Process alive or completed cleanly; checkpoints increase; rollout videos appear.

## 2. Copy New Videos And Inspect Motion
- Task: Copy rollout videos from PC to `sim/hardware01_real_calibrated_YYYYMMDD/` on Mac.
- Verify: Videos show clear thumb/finger opposition, not only caging/clamping; cube rotates with fewer jittery micro-actions.

## 3. Export New Closed-Loop Actor
- Task: Export final/best checkpoint to Mac as `sim/live_actor_export_hardware01_real_calibrated_<step>/`.
- Verify: Folder contains `actor_policy.npz`, metadata JSON, and any needed sensor normalization/proprio maps.

## 4. Export Exact `u_real_order` Trace
- Task: Export at least one matching sim video and JSON `u_real_order` trace from the selected checkpoint.
- Verify: JSON command order is `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`; video filename and trace filename share rollout id.

## 5. No-Cube Real Replay
- Task: Replay the exact trace on the mounted, clear hand without cube.
- Verify: No abort; max current stays below `4000 mA`; temp below `60 C`; motion visually matches sim posture better than old policy.

## 6. Cube Real Replay
- Task: Replay the same trace with cube placed in the known best position.
- Verify: Cube receives rolling torque instead of only being caged; log current/temp; stop if repeated `>4000 mA` current aborts.

## 7. Live Closed-Loop Test
- Task: Run exported actor through `scripts/live_policy_control.py` only after exact trace looks plausible.
- Verify: Motion remains dynamic; current logs do not show unexplained startup spikes; cube rotation improves relative to exact trace.

## Known Bugs / Risks
- Training PC repo is not git-controlled, so remote edits must be backed up manually.
- Real thumb posture is highly sensitive; too much thumb flex/abd curl clamps into palm, too little misses cube.
- Cube can jam against index/middle if placed too low or too close to fingertips.
- Serial readback can occasionally return invalid frame lengths; safe scripts recover by sending rest.
- Current local git status is mostly untracked, so do not assume `git diff` is a reliable change summary.

## Verification Before Calling Work Done
- New env compiles and smoke-tests.
- Sim video looks mechanically plausible.
- Exact trace replay without cube is safe.
- Exact trace replay with cube gives visible rolling attempt.
- Closed-loop actor artifacts are copied to Mac with reproducible command notes.
