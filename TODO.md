# TODO.md

## 1. Inspect `RealCalibrated` Videos
- Task: Open and inspect copied rollout videos in `sim/hardware01_real_calibrated_20260707/`.
- Verify: Videos show clear thumb/finger opposition, not only caging/clamping; cube rotates with fewer jittery micro-actions.
- Also verify: midrange finger postures are not only knuckle-bending in sim; look for fingertip/pad contact that resembles the real hand more closely.

Completed monitor/copy status:
- Remote training completed cleanly.
- Final checkpoint: `000157286400`.
- Final logged reward: `35.862`.
- Best logged reward observed: `37.066` at `137625600`.
- Videos copied to Mac: `sim/hardware01_real_calibrated_20260707/`.

Reference monitor command:
```bash
ssh hw@192.168.9.63
cd /home/hw/aero-hand-sim
ps -p 82740 -o pid,etime,pcpu,pmem,cmd
tail -120 runs/nohup_logs/aero_hardware01_real_calibrated_fresh_20260707_093702.log
find logs/AeroCubeRotateZAxisHardware01RealCalibrated-20260707-093704-aero_hardware01_real_calibrated_fresh_20260707_093702 -maxdepth 2 -type f | sort | tail -50
```

## 2. Export New Closed-Loop Actor
- Task: Export final/best checkpoint to Mac as `sim/live_actor_export_hardware01_real_calibrated_<step>/`.
- Verify: Folder contains `actor_policy.npz`, metadata JSON, and any needed sensor normalization/proprio maps.

## 3. Export Exact `u_real_order` Trace
- Task: Export at least one matching sim video and JSON `u_real_order` trace from the selected checkpoint.
- Verify: JSON command order is `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`; video filename and trace filename share rollout id.

## 4. No-Cube Real Replay
- Task: Replay the exact trace on the mounted, clear hand without cube.
- Verify: No abort; max current stays below `4000 mA`; temp below `60 C`; motion visually matches sim posture better than old policy.

## 5. Cube Real Replay
- Task: Replay the same trace with cube placed in the known best position.
- Verify: Cube receives rolling torque instead of only being caged; log current/temp; stop if repeated `>4000 mA` current aborts.

## 6. Live Closed-Loop Test
- Task: Run exported actor through `scripts/live_policy_control.py` only after exact trace looks plausible.
- Verify: Motion remains dynamic; current logs do not show unexplained startup spikes; cube rotation improves relative to exact trace.

## Known Bugs / Risks
- Do not double-apply the old replay scale/bias to new `RealCalibrated` traces; the calibration should already be inside the trained env/export.
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
