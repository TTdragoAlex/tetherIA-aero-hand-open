# TODO.md

## 1. Review `RealCalibratedAntiTrap` Videos
- Task: Open and inspect copied rollout videos in `sim/hardware01_real_calibrated_antitrap_20260707/`.
- Verify: Cube rotates without getting wedged tightly between thumb and index, and motion remains plausible for real hardware.
- Run id: `aero_hardware01_real_calibrated_antitrap_fresh_20260707_151203`
- Log: `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_calibrated_antitrap_fresh_20260707_151203.log`
- Final checkpoint: `000157286400`
- Final logged reward: `15.875`
- Best logged reward observed: `16.023` at `124518400`
- Copied videos:
  - `sim/hardware01_real_calibrated_antitrap_20260707/rollout0.mp4`
  - `sim/hardware01_real_calibrated_antitrap_20260707/rollout1.mp4`
  - `sim/hardware01_real_calibrated_antitrap_20260707/rollout2.mp4`

Current assistant review:
- Anti-trap appears better than the smooth run on thumb-index wedging.
- Rollout 1 looks strongest.
- The strategy still uses a shallow hand cradle/pocket, so hardware replay is not an automatic yes.

Completed monitor/copy status:
- Remote training completed cleanly.
- Final checkpoint: `000157286400`.
- Final logged reward: `35.862`.
- Best logged reward observed: `37.066` at `137625600`.
- Videos copied to Mac: `sim/hardware01_real_calibrated_20260707/`.
- Video review: not good enough for hardware replay; motion is too jittery, thumb activity is too frequent, and the cube bounces/gets trapped despite sometimes rotating.
- Smooth videos copied to Mac: `sim/hardware01_real_calibrated_smooth_20260707/`.
- Smooth video review: much better rhythm and less jitter, but rollout 1 and rollout 2 often wedge the cube between thumb and index. Train anti-trap before hardware replay.
- Anti-trap videos copied to Mac: `sim/hardware01_real_calibrated_antitrap_20260707/`.

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
- Do not double-apply the old replay scale/bias to new `RealCalibrated` traces; the calibration should already be inside the trained env/export.
- Do not replay the first `RealCalibrated` run on hardware; use it only as evidence that smoother training is needed.
- Do not replay the `RealCalibratedSmooth` run on hardware yet; it still uses a thumb-index trap/pinch strategy in some rollouts.
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
