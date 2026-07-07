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
