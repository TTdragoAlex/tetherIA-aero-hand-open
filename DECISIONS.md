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
