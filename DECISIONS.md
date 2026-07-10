# DECISIONS.md

## Decision: Use hardware01 real-order action semantics
- Decision: Policies for real transfer should use `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]` with `u in [0, 1]` where higher generally means more curl/contact.
- Why: This matches the real SDK/raw command order and reduces translation ambiguity.
- Rejected: Original sim action order `[index, middle, ring, pinky, thumb_abd, thumb_flex, thumb_tendon]` as the deployment-facing action language, because it caused repeated mapping/sign confusion.

## Decision: Keep old envs/checkpoints and add variants
- Decision: Add new envs such as `AeroCubeRotateZAxisHardware01Efficient` and `AeroCubeRotateZAxisHardware01RealCalibrated` instead of rewriting old behavior.
- Why: Old videos/checkpoints are valuable baselines and regression references.
- Rejected: Mutating `AeroCubeRotateZAxis` directly, because it would make previous results hard to interpret.

## Decision: Actor should use real-hand-available observations
- Decision: Actor uses deployable hand signals such as hardware position proxy, last action, and current/force proxy; critic can retain privileged sim state.
- Why: Real hand has no cube pose/velocity sensor right now, so deployment should not require cube vision.
- Rejected: Actor using cube pose/orientation/velocity, because it would produce a policy that cannot be run on the real setup without cameras.

## Decision: Use exact sim `u_real_order` traces to debug transfer
- Decision: Export exact rollout traces and replay them on the real hand with `scripts/replay_hardware01_u_trace_safe.py`.
- Why: This separates policy quality from live observation/control bugs and lets sim/real motion be compared from the same command sequence.
- Rejected: Only tuning live closed-loop policy, because too many variables change at once.

## Decision: Current issue is probably environment/contact mismatch, not only mapping
- Decision: Stop relying on manual replay bias/scale tuning as the main solution; fix training environment/contact assumptions.
- Why: After mapping audits and exact trace replay, the real hand receives dynamic commands and contacts the cube, but cube rotation still differs from sim.
- Rejected: Continuing small per-channel bias tweaks indefinitely, because improvements were incremental and did not solve rolling torque.

## Decision: Train a real-calibrated variant
- Decision: `AeroCubeRotateZAxisHardware01RealCalibrated` maps actor real-command `u` through real-tested scale/bias before MuJoCo ctrl.
- Why: The best real replay needed compressed thumb ranges and expanded finger ranges. Training should learn inside that command window instead of applying it only during replay.
- Rejected: Directly using the old efficient policy at full scale, because the real posture/contact window did not match sim well enough.

## Decision: Penalize clamping without rotation
- Decision: Add/strengthen stalled-force, non-thumb-force, static-clamp, and thumb-overcurl penalties gated by low cube angular velocity.
- Why: Real tests showed fingers can cage/clamp the cube without producing useful rotation.
- Rejected: Rewarding grip/holding alone, because stable holding can become the failure mode.

## Decision: Do not treat cube size as the main fix
- Decision: Keep the current cube as the working physical candidate and focus on training/contact/mapping.
- Why: Smaller and larger cubes were already tried; the current cube gave the best practical contact among tested options.
- Rejected: Spending the next iteration on cube-size changes, because the same caging/pushing behavior persisted across sizes.

## Decision: Handle midrange joint mismatch through training robustness
- Decision: Use action-to-joint randomization and real-calibrated command ranges instead of trying to hand-fit every real joint posture.
- Why: Sim and real endpoints looked usable, but `u=0.5` differed mechanically; training should learn policies robust to that nonlinear coupling mismatch.
- Rejected: Manually tuning one static midpoint, because cube rotation needs dynamic contact over the full range, not just one matched pose.

## Decision: Do not replay jittery `RealCalibrated` rollouts on hardware
- Decision: Treat the completed `AeroCubeRotateZAxisHardware01RealCalibrated` run as a learning signal, not a hardware candidate.
- Why: The rollout videos showed cube rotation through jittery finger/thumb impacts, cube bouncing, and frequent thumb motion that is unlikely to transfer through real tendon compliance, latency, backlash, and current limits.
- Rejected: Exporting/replaying the trace immediately, because the observed sim behavior is likely to become clamping, noise, or current spikes on the real hand.

## Decision: Train a smooth real-calibrated variant
- Decision: Add `AeroCubeRotateZAxisHardware01RealCalibratedSmooth` with hard `u` slew limiting, lower effective action cadence, stronger action/thumb smoothness penalties, and a cube linear-velocity penalty.
- Why: We want slow, sustained rolling torque rather than bouncing or shaking the cube until it rotates.
- Rejected: Only increasing soft action-rate penalties in the old env, because the previous policy still found high-frequency contact strategies.

## Decision: Train an anti-trap smooth variant
- Decision: Add `AeroCubeRotateZAxisHardware01RealCalibratedAntiTrap` with thumb/index trap and pinch penalties while keeping the smooth run's action-repeat and slew cap.
- Why: Smooth rollout 1 and rollout 2 rotated the cube, but often by wedging it between thumb and index. That failure mode is likely worse on the real hand because compliance, backlash, and current limits turn a simulated pinch pocket into a stuck cube.
- Rejected: Replaying the smooth trace immediately, because the videos show the right speed but the wrong contact strategy.

## Decision: Gate live policy on visual cube replay
- Date: 2026-07-08
- Decision: Treat the anti-trap rollout 1 exact trace as telemetry-safe on hardware, but do not run live closed-loop policy until the cube replay is visually judged to produce plausible rolling rather than caging, jamming, or pushing.
- Why: The no-cube and cube replays both stayed well below current and temperature abort limits, but transfer success depends on contact behavior. Safe actuator telemetry does not prove the cube is being rotated in the intended way.
- Evidence: `logs/hardware01_u_trace_replay_20260708_093016.csv` and `logs/hardware01_u_trace_replay_20260708_093326.csv` both completed 125 steps with no abort.

## Decision: Start physics identification after anti-trap replay
- Date: 2026-07-08
- Decision: Do not proceed to live policy from the current anti-trap checkpoint. Start physics/contact identification first.
- Why: Visual review of `/Users/alextang/Downloads/IMG_5309.mov` showed the cube moving slightly, but the thumb pushed it laterally off the hand before useful opposing finger contact developed. That points to a sim-real contact/geometry/support mismatch, not a command-safety problem.
- Rejected: More reward-only training from the same assumptions, because the replay failure is a structured physical mismatch rather than simple insufficient exploration.

## Decision: Train a physics-ID anti-ejection variant
- Date: 2026-07-08
- Decision: Add `AeroCubeRotateZAxisHardware01RealCalibratedPhysicsID` and train it before any live-policy export.
- Why: The seeded native sweep showed the real-like bad direction is thumb-dominant contact with weak opposing finger support. Soft spring changes alone were not enough to explain the failure. The new variant adds lateral cube-drift cost and randomizes palm/cube friction, thumb-vs-finger friction, tendon spring stiffness, and weak finger actuation.
- Rejected: Directly testing the anti-trap live actor, because the exact trace already showed thumb lateral ejection on the real hand.

## Decision: Gate PhysicsID transfer through exact trace replay
- Date: 2026-07-08
- Decision: Treat the completed `PhysicsID` videos as promising, but require exact smoothed `u_real_order` trace export and dry-run before any hardware movement or live actor export.
- Why: Rollouts 0, 1, and 2 keep the cube seated and rotating in sim without obvious thumb-side ejection, but the previous anti-trap policy also looked plausible before failing on real contact. Exact trace replay remains the safest way to isolate sim-real physics mismatch from live feedback issues.
- Rejected: Exporting the live actor immediately from the final checkpoint, because the real hand has already shown that visually acceptable sim contact can become thumb lateral ejection on hardware.

## Decision: Stop current PhysicsID transfer after thumb ejection
- Date: 2026-07-08
- Decision: Do not test the current `PhysicsID` checkpoint as a live actor and do not treat rollout 1 or 2 as direct next candidates.
- Why: Rollout 0 exact replay was electrically safe but still pushed the cube off by the thumb. Rollout 1 has a higher thumb-flex range and rollout 2 has wider finger excursions, so they are unlikely to solve a thumb-ejection failure as direct candidates.
- Rejected: Continuing through the remaining `PhysicsID` rollouts, because the repeated failure mode is now specific enough to require a thumb-lateral diagnostic or a new thumb-limited/anti-ejection training variant.

## Decision: Use the operator-tuned replay as the next command-window target
- Date: 2026-07-08
- Decision: Build the next training variant around the operator-tuned PhysicsID rollout 0 transform rather than treating replay-time channel overrides as the final deployment method.
- Why: The mostly working real replay needed very low thumb flex/tendon, broad thumb abduction, and a high compressed index baseline. This is a structured sim-to-real command/contact mismatch: sim did not trap the cube, while the real hand did unless the command window was changed substantially.
- Rejected: Continuing manual channel tuning as the main path, because that improves one trace but does not teach a deployable policy to avoid the real trap modes.

## Decision: Train RealTunedWindow before live export
- Date: 2026-07-08
- Decision: Add and train `AeroCubeRotateZAxisHardware01RealTunedWindow`, which bakes the operator-tuned replay transform into the sim action calibration and adds ring-pocket plus tuned-command-window penalties.
- Why: The one-minute replay worked about 80% of the time only after a large real command transform. Training inside that command window gives the policy a chance to learn robust timing/contact without permanent replay-time overrides.
- Rejected: Exporting a live actor from raw `PhysicsID`, because exact replay required substantial real-side transformation to work.

## Decision: Pause sim-success policy variants until the real failure is reproduced in sim
- Date: 2026-07-09
- Decision: Stop treating new reward/window variants that only look good in simulation as the next main path. The next work should be sim-real identification: reproduce the real thumb/finger trapping and lateral ejection in sim using exact traces, geometry/contact/compliance changes, and measured hand behavior.
- Why: `RealTunedWindow` baked in the best operator-tuned replay transform and produced plausible seated cube rotation in sim, but real replay still showed the same bad behavior. This means the translation/model mismatch is now the bottleneck.
- Rejected: Training another reward-only policy variant from the current simulator assumptions, because the simulator is not yet predicting the real failure mode.

## Decision: Feed the ball actor measured position and baseline-corrected current
- Date: 2026-07-10
- Decision: The 45 mm ball live actor should use physical `GET_POS` plus signed
  current residual above a per-servo no-object current-vs-position baseline.
- Why: The first live controller setup fed its own command as position and a
  fixed policy-mean force value. That removed contact feedback and produced a
  repeated movement unlike the simulated rollout. The actor's no-object force
  input now remains at its trained mean, while changed current can perturb it.
- Evidence: `logs/channel_friction_sweep_20260626_105220.csv` captures the new
  spring configuration, and offline checks verified that its baseline maps
  exactly to the exported actor's force mean.
- Limitation: This is a first-order preload correction, not a calibrated
  physical contact force. Thumb-flex data was protected from high current and
  is held beyond its final measured position.
- Rejected: Feeding raw current directly, because spring preload alone can
  dominate current even without an object.
