# TODO.md

## 1. Review 2026-07-08 Anti-Trap Cube Replay
- Task: Use the operator's visual observation of the cube replay to decide whether the trace produced real rolling torque or only caging/pushing.
- Verify: Cube rotates at least intermittently without sustained thumb-index trapping or repeated jamming.
- Trace: `sim/hardware01_real_calibrated_antitrap_trace_20260707/hardware01_antitrap_rollout1_u_trace.json`
- No-cube log: `logs/hardware01_u_trace_replay_20260708_093016.csv`
- Cube log: `logs/hardware01_u_trace_replay_20260708_093326.csv`
- Result: Failed as a transfer candidate. In `/Users/alextang/Downloads/IMG_5309.mov`, the cube moves slightly but the thumb pushes it laterally off the hand.
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

## 2. Export `PhysicsID` Exact Trace
- Task: Export exact `u_real_order` rollout trace from `AeroCubeRotateZAxisHardware01RealCalibratedPhysicsID` after env smoothing.
- Run id: `aero_hardware01_real_calibrated_physics_id_fresh_20260708_104812`
- Preferred checkpoint: start with final `000157286400`, because the copied videos appear to come from the final policy and look stable. Consider also rendering/exporting best reward checkpoint `000144179200` if final trace replay is questionable.
- Log: `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_calibrated_physics_id_fresh_20260708_104812.log`
- Verify: order is `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`; trace field is smoothed `u_real_order`; no replay-time scale/bias is applied.

## 3. Dry-Run `PhysicsID` Replay
- Task: Run `scripts/replay_hardware01_u_trace_safe.py` without `--run` on the exported trace.
- Verify: max step delta is compatible with `--max-step-delta 0.08`, thumb/index ranges do not look extreme, and no old channel scale/bias is applied.

Completed monitor/copy/review status:
- Remote training completed cleanly.
- Final checkpoint: `000157286400`.
- Final logged reward: `11.216`.
- Best logged reward observed: `11.654` at `144179200`.
- Videos/config/log copied to Mac: `sim/hardware01_real_calibrated_physics_id_20260708/`.
- Video review: rollouts 0, 1, and 2 keep the cube seated and rotating in sim without obvious thumb lateral ejection in sampled frames.

## 4. Export New Closed-Loop Actor Only After Physics Fix
- Task: Export final/best checkpoint to Mac as `sim/live_actor_export_hardware01_real_calibrated_<step>/`.
- Verify: Folder contains `actor_policy.npz`, metadata JSON, and any needed sensor normalization/proprio maps.

## 5. Live Closed-Loop Test
- Task: Run exported actor through `scripts/live_policy_control.py` only after exact trace looks plausible.
- Verify: Motion remains dynamic; current logs do not show unexplained startup spikes; cube rotation improves relative to exact trace.

## Known Bugs / Risks
- Do not double-apply the old replay scale/bias to new `RealCalibrated` traces; the calibration should already be inside the trained env/export.
- Do not replay the first `RealCalibrated` run on hardware; use it only as evidence that smoother training is needed.
- Do not replay the `RealCalibratedSmooth` run on hardware yet; it still uses a thumb-index trap/pinch strategy in some rollouts.
- Do not proceed to live policy solely because telemetry passed; visual cube behavior must show plausible rolling first.
- Do not proceed with the current anti-trap checkpoint as a live-policy candidate; replay video shows thumb lateral ejection.
- Use the corrected seeded physics sweep at `sim/physics_id_antitrap_rollout1_native_seeded_20260708/`; the earlier unseeded native sweep started from the wrong cube placement.
- Training PC repo is not git-controlled, so remote edits must be backed up manually.
- Real thumb posture is highly sensitive; too much thumb flex/abd curl clamps into palm, too little misses cube.
- Cube can jam against index/middle if placed too low or too close to fingertips.
- Serial readback can occasionally return invalid frame lengths; safe scripts recover by sending rest.
- Current local git status is mostly untracked, so do not assume `git diff` is a reliable change summary.

## Verification Before Calling Work Done
- New env compiles and smoke-tests.
- Sim video looks mechanically plausible.
- Exact trace replay without cube is safe. Completed 2026-07-08, max sampled current `1436.5 mA`, max temp `35 C`.
- Exact trace replay with cube gives visible rolling attempt. Telemetry completed 2026-07-08, max sampled current `1436.5 mA`, max temp `36 C`; visual review failed because the thumb pushed the cube off the hand.
- Closed-loop actor artifacts are copied to Mac with reproducible command notes.
