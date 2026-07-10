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

## 2. PhysicsID Exact Replay Result
- Task: Use exact `u_real_order` rollout trace from `AeroCubeRotateZAxisHardware01RealCalibratedPhysicsID` after env smoothing.
- Run id: `aero_hardware01_real_calibrated_physics_id_fresh_20260708_104812`
- Checkpoint: `000157286400`
- Trace dir: `sim/hardware01_real_calibrated_physics_id_trace_20260708/`
- Verify: order is `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`; trace field is smoothed `u_real_order`; no replay-time scale/bias is applied.
- Result: rollout 0 was safest by range and replay telemetry was safe, but the cube was still pushed off by the thumb. Do not proceed to live actor export.

## 3. Choose Next Thumb-Ejection Diagnostic
- Option A: Run one deliberately thumb-attenuated rollout 0 diagnostic with cube to test whether reducing thumb lateral authority keeps the cube seated. This is a diagnostic override, not a deployable policy result.
- Option B: Skip more hardware diagnostics and train a new thumb-limited / anti-ejection env that explicitly penalizes high thumb abduction/lateral cube drift and strengthens opposing finger/palm support assumptions.
- Verify: success is not just less ejection; the cube should remain seated while receiving visible rolling torque.
- Current best operator-tuned replay:
  - Preset: `physics_id_rollout0_real_hand_fitted`
  - `--channel-scale thumb_abd=0.90,thumb_flex=0.5,thumb_tendon=0.6,index=0.50,middle=0.7`
  - `--channel-bias thumb_abd=-0.04,thumb_flex=-0.32,thumb_tendon=-0.14,index=0.34,middle=0.12,pinky=0.04`
  - Dry-run ranges: thumb_abd `0.326-0.864`, thumb_flex `0.105-0.319`, thumb_tendon `0.241-0.478`, index `0.681-0.961`, middle `0.304-0.718`, ring `0.370-0.772`, pinky `0.445-0.826`.
  - Operator result: mostly working, but still not final policy; use this as the command-window target for the next sim/training variant.

Completed monitor/copy/review status:
- Remote training completed cleanly.
- Final checkpoint: `000157286400`.
- Final logged reward: `11.216`.
- Best logged reward observed: `11.654` at `144179200`.
- Videos/config/log copied to Mac: `sim/hardware01_real_calibrated_physics_id_20260708/`.
- Video review: rollouts 0, 1, and 2 keep the cube seated and rotating in sim without obvious thumb lateral ejection in sampled frames.
- Hardware result: rollout 0 still pushed the cube off by the thumb even though telemetry stayed safe. Sim still does not model the real lateral thumb failure strongly enough.
- Manual transform result: lowering thumb flex/tendon much more and raising/compressing index support made rollout 0 look mostly working on the real hand. The next training variant should train inside this transformed command window rather than rely on replay-time overrides.

## 4. RealTunedWindow Transfer Result
- Task: Check remote PID/log/checkpoints/videos for `AeroCubeRotateZAxisHardware01RealTunedWindow`.
- Run id: `aero_hardware01_real_tuned_window_fresh_20260708_165830`
- Log: `/home/hw/aero-hand-sim/runs/nohup_logs/aero_hardware01_real_tuned_window_fresh_20260708_165830.log`
- Run dir: `/home/hw/aero-hand-sim/logs/AeroCubeRotateZAxisHardware01RealTunedWindow-20260708-165832-aero_hardware01_real_tuned_window_fresh_20260708_165830`
- Result: completed cleanly, final/best reward `6.621` at checkpoint `000157286400`.
- Copied videos: `sim/hardware01_real_tuned_window_20260708/`.
- Copied traces: `sim/hardware01_real_tuned_window_trace_20260708/`.
- Real replay result: still bad, with the same trap/ejection transfer failure as before. Do not export or test this live actor.

## 5. Sim-Real Identification Plan
- Task: Make the simulator reproduce the real failure on exact traces before training another policy.
- Inputs:
  - RealTunedWindow traces: `sim/hardware01_real_tuned_window_trace_20260708/`.
  - Best manual replay command window from PhysicsID rollout 0, packaged as `--preset physics_id_rollout0_real_hand_fitted`.
  - User visual result: RealTunedWindow still fails in the same way, so sim-success is not predictive yet.
- First target: replay exact traces in sim under modified contact/geometry/compliance assumptions until the sim also traps/ejects the cube like reality.
- Candidate variables:
  - thumb lateral contact geometry and collision shape,
  - palm support/cube seating geometry,
  - index/ring/middle contact support and compliance,
  - tendon spring stiffness/damping and midrange joint coupling,
  - cube/skin friction and contact softness,
  - servo latency/deadband/backlash.
- Acceptance: a replay trace that looks good in current sim should fail in the modified sim in the same direction as the real hand, and the manual-tuned replay should score better than the failed exact trace.

## 6. Ball45 Training Series
- Task: Train a new series using a 45 mm ball instead of a cube.
- Env: `AeroBall45mmRotateZAxisHardware01RealTunedWindow`
- Run id: `aero_ball45_real_tuned_window_fresh_20260710_093242`
- PID: `127699`
- Log: `/home/hw/aero-hand-sim/runs/nohup_logs/aero_ball45_real_tuned_window_fresh_20260710_093242.log`
- Run dir: `/home/hw/aero-hand-sim/logs/AeroBall45mmRotateZAxisHardware01RealTunedWindow-20260710-093244-aero_ball45_real_tuned_window_fresh_20260710_093242`
- Local source snapshot: `sim/ball45_real_tuned_window_remote_source_20260710/`
- Verify: rollout videos should show marker-dot spin, not just ball translation.
- Acceptance: ball stays seated and rotates reliably without being ejected by the thumb; if this works, compare the learned contact strategy against cube failures.

## 7. Export New Closed-Loop Actor Only After Sim-Real Identification
- Task: Export final/best checkpoint to Mac as `sim/live_actor_export_hardware01_real_tuned_window_<step>/`.
- Verify: Folder contains `actor_policy.npz`, metadata JSON, and any needed sensor normalization/proprio maps.

## 8. Live Closed-Loop Test
- Task: Run exported actor through `scripts/live_policy_control.py` only after exact trace looks plausible.
- Verify: Motion remains dynamic; current logs do not show unexplained startup spikes; cube rotation improves relative to exact trace.

## Known Bugs / Risks
- Do not double-apply the old replay scale/bias to new `RealCalibrated` traces; the calibration should already be inside the trained env/export.
- Do not replay the first `RealCalibrated` run on hardware; use it only as evidence that smoother training is needed.
- Do not replay the `RealCalibratedSmooth` run on hardware yet; it still uses a thumb-index trap/pinch strategy in some rollouts.
- Do not proceed to live policy solely because telemetry passed; visual cube behavior must show plausible rolling first.
- Do not proceed with the current anti-trap checkpoint as a live-policy candidate; replay video shows thumb lateral ejection.
- Do not proceed with the current PhysicsID checkpoint as a live-policy candidate; exact replay still shows thumb lateral ejection on real hardware.
- Do not proceed with the current RealTunedWindow checkpoint as a live-policy candidate; it still fails in real replay despite plausible sim videos.
- Do not test PhysicsID rollout 1 or rollout 2 as direct candidates unless deliberately diagnosing range effects; rollout 1 has more thumb flex and rollout 2 has wider finger motion.
- Do not treat the best manual transform as the final solution; it reveals the sim-to-real command/contact mismatch that should be built into training.
- Do not train more reward-only/window variants until the simulator can reproduce the real trapping/ejection failure from exact traces.
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
