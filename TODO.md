# TODO.md

## 0. Build Coupled-Posture Current Calibration For The Ball Actor

- Result: failed on 2026-07-10. Two no-object tests hit safety aborts and made
  a repeated clamp/release motion. The ball actor is blocked from hardware use.
- Evidence: `logs/live_policy_control_20260710_154431.csv` and
  `logs/live_policy_control_20260710_154443.csv` show no-object index current
  of roughly `3.3-3.4 A` near the actor's mean index posture, far above the
  one-channel baseline for the same index value.
- Task: collect a safe no-object dataset through coupled seven-servo postures
  inside the known low-current real-hand-fitted window; fit each current to the
  full posture, not only its own servo position.
- Verify: no-object predicted residual current remains near zero across the
  full calibration trajectory before any live actor is unblocked.
- Collector: `scripts/collect_hardware01_coupled_baseline_safe.py` samples
  sparse postures from the fitted trace, logs every ramp step, skips at
  `1800 mA`, hard-aborts at `3000 mA`, and returns to rest after every pose.
  Start with a dry run; the first physical session must use `--max-poses 1`.
- Stage 1 result: pose `0` completed in
  `logs/coupled_current_baseline_20260710_160835.csv`; peak ramp current was
  `1124.5 mA`, settled maximum was `1040 mA`, and maximum temperature was
  `41 C`. The next safe probe may use `--max-poses 2`, which repeats the known
  safe pose `0` before collecting one additional pose.
- Stage 2 result: `logs/coupled_current_baseline_20260710_162258.csv` repeated
  pose `0` and added pose `12`; both remained below `1124.5 mA` during ramps,
  the new pose settled at `1033.5 mA`, and the final temperature was `43 C`.
  The next safe probe may use `--max-poses 3` to add source pose `24`.
- Stage 3 result: `logs/coupled_current_baseline_20260713_095103.csv` added
  source pose `24`; all three poses completed below `1040 mA` during ramps and
  `35 C`. Before adding pose `36`, the collector now records eight settled
  telemetry samples per pose to measure normal current fluctuation directly.
- Stage 4 result: `logs/coupled_current_baseline_20260713_095516.csv` held
  source poses `0`, `12`, `24`, and `36` for eight settled readings each. All
  completed safely; per-channel standard deviation was `6.4-38.0 mA`, the
  widest within-pose span was `97.5 mA`, and maximum temperature was `37 C`.
  This supports a full-posture baseline using a median and measured spread.
  The next probe may use `--max-poses 5`, repeating these four poses and adding
  source pose `48`.
- Stage 5 result: `logs/coupled_current_baseline_20260713_095924.csv` repeated
  source poses `0-36` and added source pose `48`. All five poses completed with
  eight settled readings each; the held peak was `1033.5 mA` and maximum
  temperature was `40 C`. The next probe may use `--max-poses 6` to add source
  pose `60`, completing the initial six-pose coverage set.
- Stage 6 result: `logs/coupled_current_baseline_20260713_100341.csv` repeated
  source poses `0-48` and added source pose `60`. All six poses completed with
  eight settled readings each; the largest held current was `1092 mA` and
  maximum temperature was `42 C`. Initial collection is complete.
- Next: build and evaluate an offline coupled-current baseline that predicts
  all seven no-object currents from the seven-command posture, retains
  per-channel uncertainty, and rejects positions outside the measured window.
  Do not unblock or rerun the ball actor yet: six safe postures establish the
  method but do not cover arbitrary actor movement.
- Offline artifact result: `scripts/build_coupled_observation_calibration.py`
  generated `sim/hand_coupled_observation_calibration_20260713.json` from the
  settled samples across the four-, five-, and six-pose runs. It contains six
  posture/current distributions and enforces a future `0.08` nearest-pose
  support radius. Validation passed, but the artifact is `offline_only` and is
  intentionally not wired into `scripts/live_policy_control.py`.
- Next: design a holdout validation and expand posture coverage before deciding
  whether a guarded current-residual adapter is useful enough to integrate.
- Holdout result: `scripts/evaluate_coupled_observation_calibration.py` wrote
  `sim/hand_coupled_observation_validation_20260713.json`. Across 14
  leave-one-session-out repeated-pose cases, per-channel median absolute
  residual was `4.1-16.3 mA`; the largest residual was `82.9 mA` on ring.
  Source pose `60` remains unvalidated because it appears in one session.
- Next: select and collect additional safely separated posture samples, then
  repeat the temporal validation. Keep the ball actor blocked until both
  posture coverage and no-object residual behavior are adequate.
- Prepared next physical task: dry-run of collector index `6` selects source
  step `72`, target `[0.620, 0.144, 0.305, 0.730, 0.426, 0.688, 0.724]`.
  Run it alone with `--start-pose-index 6 --max-poses 1`; keep the hand empty.
- Result: source step `72` completed in
  `logs/coupled_current_baseline_20260713_101750.csv` with eight settled
  readings, `1056.2 mA` held maximum, and `40 C` maximum temperature. The
  calibration now contains steps `0-72`; repeat source `72` in a later session
  before treating it as temporally validated. Next safe coverage candidate is
  source step `84` at collector index `7`.
- Result: source step `84` completed in
  `logs/coupled_current_baseline_20260713_102428.csv` with eight settled
  readings, `1124.5 mA` held maximum, and `41 C` maximum temperature. The next
  no-object coverage candidate is source step `96` at collector index `8`.

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
- Task: Train and review a new series using a 45 mm ball instead of a cube.
- Env: `AeroBall45mmRotateZAxisHardware01RealTunedWindow`
- Run id: `aero_ball45_real_tuned_window_fresh_20260710_093242`
- Log: `/home/hw/aero-hand-sim/runs/nohup_logs/aero_ball45_real_tuned_window_fresh_20260710_093242.log`
- Run dir: `/home/hw/aero-hand-sim/logs/AeroBall45mmRotateZAxisHardware01RealTunedWindow-20260710-093244-aero_ball45_real_tuned_window_fresh_20260710_093242`
- Local source snapshot: `sim/ball45_real_tuned_window_remote_source_20260710/`
- Copied videos/config/log: `sim/ball45_real_tuned_window_20260710/`
- Corrected visual videos/log/XML: `sim/ball45_real_tuned_window_visualfix_20260710/`
- Live actor export: `sim/live_actor_export_ball45_real_tuned_window_000157286400/`
- Result: completed cleanly at checkpoint `000157286400`; final reward `39.298`, best observed reward `39.676` at `137625600`.
- Initial video correction: the first videos made the ball look like a tiny dot because only the marker rendered clearly. The visual-fix videos show the full 45 mm ball.
- Next verification: no-cube live actor test at `--playback-scale 0.05`; only then test with the 45 mm ball.

## 7. Export New Closed-Loop Actor Only After Sim-Real Identification
- Status: 45 mm ball actor exported to `sim/live_actor_export_ball45_real_tuned_window_000157286400/`.
- Verify: Folder contains `actor_policy.npz`, metadata JSON, and README with first no-cube command.

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
