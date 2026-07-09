# Problem / Fix Log

This file tracks the major problems encountered while bringing the TetherIA/Aero hand from basic hardware control toward sim-to-real cube rotation. Each section starts with the plain version first, then adds technical details where useful.

## High Empty-Hand Current (6/15-6/25)

### Test Setup
- Swept each servo from `0.0 -> 0.9`.
- Step size: `0.05`.
- `skip_current = 2500 mA`.
- `emergency_current = 3500 mA`.
- Thumb abduction servo had no spring; other fingers/thumb tendons had springs.

### Key Data
- `thumb_abd`: max `396.5 mA` at target `0.40`.
- `thumb_flex`: max `2678.0 mA` at target `0.65`, skipped due to high current.
- `thumb_tendon`: max `2717.0 mA` at target `0.85`, skipped due to high current.
- `index`: max `1241.5 mA` at target `0.75`.
- `middle`: max `1248.0 mA` at target `0.75`.
- `ring`: max `1657.5 mA` at target `0.90`.
- `pinky`: max `1807.0 mA` at target `0.90`.

Source log: `logs/channel_friction_sweep_20260616_143421.csv`.

### Problem
The spring-loaded servos showed much higher current than the non-spring thumb abduction servo.

Simple explanation: the motors were fighting the springs even when the hand was empty. The thumb abduction servo did not have that spring load, so it stayed much cooler electrically.

Technical details:
- `thumb_abd` stayed under `400 mA` across the sweep.
- Several spring-loaded channels exceeded `1.2-1.8 A`.
- `thumb_flex` and `thumb_tendon` exceeded `2.5 A`, triggering skip protection.
- This supported the hypothesis that spring force / mechanical preload was a major contributor to high idle or movement current.

### Solution
New springs with better dimensions/materials were installed.

### Before / After Spring Change Comparison

| Servo | Before max current | After max current | Change |
| --- | --- | --- | --- |
| `thumb_abd` | `396.5 mA` | `461.5 mA` | Slightly higher, still low |
| `thumb_flex` | `2678.0 mA` at `0.65` | `2639.0 mA` at `0.25` | Basically unchanged / still problematic |
| `thumb_tendon` | `2717.0 mA` at `0.85` | `2684.5 mA` at `0.85` | Still problematic at large target values |
| `index` | `1241.5 mA` | `1020.5 mA` | Improved |
| `middle` | `1248.0 mA` | `962.0 mA` | Improved |
| `ring` | `1657.5 mA` | `1228.5 mA` | Improved |
| `pinky` | `1807.0 mA` | `1280.5 mA` | Improved |

Source log: `logs/channel_friction_sweep_20260626_105220.csv`.

### Simple Summary
- The new springs improved the four fingers clearly.
- `index`, `middle`, `ring`, and `pinky` dropped by roughly `18-29%`.
- The thumb tendon channels did not meaningfully improve.
- `thumb_flex` still reached about `2.6-2.7 A`.
- The biggest remaining high-current issue is the thumb flex/tendon mechanism, not the four fingers.
- The current became low enough to proceed with full-hand tests, but thumb channels still deserve caution.

## Low Thumb Participation (6/25-6/26)

### Problem
The thumb did not participate enough in cube rotation, especially `thumb_abd` / servo 0.

Simple explanation: the thumb stayed too far away from the palm and cube. The fingers could touch the cube, but the thumb was not coming around to oppose them, so the hand could not create a useful pinch/rolling motion.

Technical details:
- In real tests, `thumb_abd` barely moved toward the cube.
- In sim videos, the thumb appeared to move toward the palm and help rotate the cube.
- This meant the real thumb was not playing the same role as the simulated thumb.

### Reason
A sign mismatch was found in the sim-to-real interpretation for thumb abduction.

Simple explanation: the same thumb command meant “move this way” in one place and “move the opposite way” in another place.

Technical detail:
- Simulated `thumb_abd` useful motion was effectively in the `0 -> -1.0` direction in the original sim action language.
- The real hand needed increasing `thumb_abd` values to bring the thumb toward the palm/cube.

### Solution
The `thumb_abd` sign/mapping was flipped in the sim-to-real mapping experiments.

### Result
- Thumb motion became visibly better.
- However, simply biasing or flipping the thumb was not enough to solve cube rotation.
- This led to deeper mapping audits and eventually the hardware-style action-space work.

## Incorrect Translation Of Servo Command (6/26-7/2)

### Problem
The policy looked good in simulation, but when transferred to the real hand the motion was too small, too static, or wrong in character.

Simple explanation: the simulated hand and the real hand were not speaking the same “movement language.” A command that made the sim finger curl strongly might become a weak or different real-hand command.

Technical details:
- Original sim action order was:
  `[index, middle, ring, pinky, thumb_abd, thumb_flex, thumb_tendon]`.
- Real hardware command order is:
  `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`.
- Original sim formula was:
  `sim_ctrl = home_ctrl + sim_action * action_scale`.
- Confirmed installed values:
  - `home_ctrl = [0.09, 0.09, 0.09, 0.09, 0.75, 0.035, 0.1]`.
  - `action_scale = [0.02, 0.02, 0.02, 0.02, 0.7, 0.003, 0.012]`.
- For sim tendon channels, positive original sim action lengthened/opened tendons and negative action shortened/curled them.
- For real hardware-style commands, higher values are closer to more curl/contact.

### Attempts
- Several mapping tournament candidates were tested.
- Candidate families included centered mappings, all-positive mappings, absolute/contact mappings, XML ctrl-range mappings, and wider thumb mappings.
- Mapping audit passed basic static checks: `28` tests passed, `0` failed.
- Exact sim traces were exported and replayed on the real hand to remove live-policy feedback as a confounding variable.

### Solution
A new hardware-style action convention was created.

Simple explanation: instead of constantly translating between sim language and hand language, the policy should directly output hand-like commands.

Technical details:
- New hardware01 policy action order:
  `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`.
- New command semantics:
  - `0 = open/release`.
  - `0.5 = home/contact-ready`.
  - `1 = curl/contact`.
- This preserved old sim envs while adding new variants for comparison.

### Result
- Real-hand motion became more understandable and easier to debug.
- The hand could receive dynamic commands.
- The remaining problem shifted from “wrong mapping” toward “sim contact/training does not match real contact well enough.”

## Initial Servo Connection / Hardware Communication Failure (Early June)

### Problem
At first, the software could run, but the servos did not properly connect/respond.

Simple explanation: this looked like a software or GUI problem at first, but the real issue was physical electrical connection quality.

Technical details:
- `GET_TEMP` initially returned `0`, which suggested the hand was not actually communicating with the servos correctly.
- The likely issue was poor soldering/connection on the XIAO/carrier board pins used for serial communication.
- The relevant serial pins were `SERIAL2_TX_PIN = GPIO3` and `SERIAL2_RX_PIN = GPIO2`.
- The servo bus needed both communication and proper external servo power; USB/logic power alone was not enough for reliable servo operation.

### Solution
The hardware connection/soldering issue was fixed.

### Result
- Servo temperature readings became valid.
- All servos could be detected and controlled.
- GUI sliders successfully moved all fingers.
- This confirmed the GUI was not the main blocker at that stage.

## High Idle Current And High-Pitched Servo Noise (6/9-6/15)

### Problem
The hand made a high-pitched sound, and some servos showed high current even when the hand was supposed to be resting/open.

Simple explanation: the servos were buzzing because they were constantly trying to hold or reach a position that was mechanically uncomfortable or not exactly where the hand actually sat.

Technical details:
- Higher idle current usually correlated with louder high-pitched servo noise.
- Lower current often happened when `GET_POS` was closer to the commanded slider/target value.
- Raw rest calibration helped reduce command/position mismatch.
- However, some channels still had persistent current even near rest, suggesting mechanical preload, spring tension, tendon routing, or homing offset.

### Attempts
- Used `Load Current GET_POS` style logic to send current positions as raw targets.
- Saved raw rest values to `aero_hand_calibration.json`.
- Removed the older “Quiet Thumb Rest” preset because it was not reliable enough.
- Current probes and idle logs were collected under `logs/aero_idle_probe_*.csv` and `logs/servo_current_profile_*.csv`.

### Solution
A raw rest calibration flow was kept, but not treated as a complete fix.

### Result
- Rest/idle behavior improved enough to continue testing.
- The problem was not considered fully solved by software alone.
- Later spring/current sweeps showed mechanical load was a major contributor.

## GUI / Mac Compatibility Issue (Early June)

### Problem
The TetherIA GUI needed small local fixes to run smoothly on macOS.

Simple explanation: the GUI was written with assumptions that work on some systems but not perfectly on Mac.

Technical details:
- Tk's `-zoomed` window attribute is not supported on macOS.
- This could make the GUI launch fail or behave oddly.

### Solution
Added a Mac patch script:
- `scripts/patch_aero_gui_macos.py`.
- `launch_gui.sh` runs the patch before launching the GUI.

### Result
- GUI launch became more reliable on the Mac.
- GUI was useful for manual slider testing, but later sim-to-real policy testing moved mostly to scripts for repeatability and logging.

## Serial Readback / Invalid Frame Issues

### Problem
Some real-hand tests occasionally failed because the hand returned an invalid or unexpected response frame.

Simple explanation: the computer asked the hand for data, but the reply packet was malformed, incomplete, or not the expected length.

Technical details:
- Example failure: `Invalid response from hand in get_actuator_currents. Expected 36, got 91`.
- This happened during replay/current sampling, not necessarily because the hand physically jammed.
- Serial timing, stale bytes, or firmware/protocol framing could cause occasional bad reads.

### Solution
Safe scripts were written to recover instead of leaving the hand in a commanded posture.

Technical details:
- `scripts/aero_hand_control.py` centralizes serial commands/readbacks.
- Safe replay scripts catch exceptions and send raw rest during recovery.
- Important scripts log telemetry to CSV for later inspection.

### Result
- Bad serial frames became annoying but not catastrophic.
- Tests could be repeated safely after recovery.

## Cube Is Touched But Not Rotated (6/29-7/6)

### Problem
Policies could move the hand and touch the cube, but the cube usually did not rotate meaningfully in the real world.

Simple explanation: the real hand was mostly pushing, holding, or caging the cube. In simulation, the same general behavior looked like useful rolling because the simulated contact/friction/posture was more favorable.

Technical details:
- Sim videos showed thumb/finger opposition and useful cube spin.
- Real exact-trace tests showed the hand could contact and slightly move the cube, but not reliably rotate it.
- The cube often got trapped between fingers or against the palm instead of being rolled.
- The user tried smaller and larger cubes; cube size was not considered the main fix. The best physical cube tried so far is about `5.4 cm` side length.

### Attempts
- Tried open-loop exact sim trace replay.
- Tried live closed-loop policy control.
- Tried different thumb bias/scale and finger scale changes.
- Compared sim rollout videos with real phone videos.
- Tested with and without cube.

### Solution Direction
The fix was moved back into training/environment design.

Simple explanation: instead of manually tweaking the real hand after training, train the simulated hand under conditions that better match the real hand.

Technical details:
- Created `AeroCubeRotateZAxisHardware01RealCalibrated` on the Ubuntu training PC.
- Added real-tested command calibration inside training:
  - `scale = [0.21, 0.21, 0.315, 1.35, 1.35, 1.25, 1.20]`.
  - `bias = [-0.12, -0.22, -0.18, 0.0, 0.0, 0.0, 0.0]`.
- Added/strengthened penalties for:
  - stalled force,
  - non-thumb force,
  - static clamping,
  - thumb overcurl.
- Increased domain/action randomization around contact and command coupling.

### Result
- The first `RealCalibrated` run completed and produced rollout videos plus an actor export.
- Video review showed jittery finger/thumb impacts and cube bouncing, so it was not treated as a hardware candidate.
- For the new `RealCalibrated` policy, do not double-apply the old replay scale/bias unless intentionally doing a diagnostic override.
- This led to the smoother, anti-trap, PhysicsID, and RealTunedWindow variants.

## Sim Midpoint Posture Does Not Match Real Midpoint (7/3-7/6)

### Problem
The sim and real hand looked acceptable at command endpoints, but not at the middle command value.

Simple explanation: when both hands were commanded to about `0.5`, the real fingers bent through multiple joints, while the simulated fingers mostly bent at the knuckles. So even if open and closed positions were okay, the path between them was different.

Technical details:
- `u=0` and `u=1` diagnostics looked broadly acceptable.
- At `u=0.5`, the real hand had more distributed joint bending.
- At `u=0.5`, sim finger posture looked more concentrated around knuckle joints.
- This means the same `u` command can produce different contact geometry in the middle of the movement.

### Solution Direction
Use data/statistics and training randomization rather than hand-fitting one pose.

Technical details:
- Action-to-joint coupling randomization was added/used so the policy does not rely on one exact simulated finger shape.
- The real-calibrated environment uses command-window calibration and stronger randomization to make the policy more robust.
- Spring strength/friction was investigated as a likely contributor to the midpoint difference.

### Result
- Later sim variants produced smoother and more stable-looking motion.
- However, real replay still showed trapping/ejection failures, so midpoint mismatch remains part of the broader sim-real identification problem rather than a fully solved item.

## Open-Loop Replay vs Closed-Loop Real Policy

### Problem
Some tests replayed a fixed sim command sequence, while others ran the policy live using real hand observations. These are not the same kind of test.

Simple explanation: open-loop replay is like playing back a recorded song. Closed-loop policy control is like the hand listening to itself and choosing the next command as it moves.

Technical details:
- Exact trace replay uses recorded `u_real_order` commands from sim and sends them to the real hand.
- Live policy control uses actor observations such as position/current proxy and last action.
- The current actor does not use real cube pose because there is no camera/vision input.

### Why This Matters
- Open-loop replay is best for checking whether sim commands translate correctly to real motion.
- Closed-loop control is needed for real deployment, but it can hide whether the problem is mapping, observation, or policy behavior.

### Current Decision
Use exact trace replay first for any new policy, then try live control only if the exact trace looks mechanically plausible and safe.

## Later Sim Variants Still Did Not Transfer (7/7-7/9)

### Problem
After the command-language fixes, several policies looked increasingly plausible in simulation but still failed on the real hand.

Simple explanation: the simulator learned ways to rotate the cube that the real hand could not reproduce. The sim hand could appear to roll the cube, while the real hand trapped, caged, or pushed the cube away.

### Attempts
- `AeroCubeRotateZAxisHardware01RealCalibrated`: trained in a real-tested command window; rejected because the sim strategy was too jittery/bouncy.
- `AeroCubeRotateZAxisHardware01RealCalibratedSmooth`: added action smoothing and linear-velocity penalties; smoother, but often used a thumb-index pocket.
- `AeroCubeRotateZAxisHardware01RealCalibratedAntiTrap`: added thumb/index trap and pinch penalties; exact replay was electrically safe but visually failed because the thumb pushed the cube laterally off the hand.
- `AeroCubeRotateZAxisHardware01RealCalibratedPhysicsID`: widened physics randomization and penalized planar cube drift; looked good in sim but still failed exact real replay.
- `AeroCubeRotateZAxisHardware01RealTunedWindow`: baked the best operator-tuned replay window into training; looked plausible in sim but still failed on real replay.

### Result
- More reward/window tuning alone is no longer considered the main path.
- The current bottleneck is that the simulator does not reproduce the real failure mode well enough.
- The next main work is sim-real identification: replay exact traces in sim and change geometry/contact/compliance until the sim fails in the same direction as the real hand.

## Current Best Real-Hand Fitted Replay (7/9)

### What It Is
The current best real-hand result is a fitted open-loop replay preset, not a trained closed-loop policy.

Preset:

```bash
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --preset physics_id_rollout0_real_hand_fitted
```

### Source
- Trace:
  `sim/hardware01_real_calibrated_physics_id_trace_20260708/hardware01_physics_id_rollout0_u_trace.json`
- Scale:
  `thumb_abd=0.90,thumb_flex=0.5,thumb_tendon=0.6,index=0.50,middle=0.7`
- Bias:
  `thumb_abd=-0.04,thumb_flex=-0.32,thumb_tendon=-0.14,index=0.34,middle=0.12,pinky=0.04`

### Dry-Run Ranges
- thumb_abd: `0.326-0.864`
- thumb_flex: `0.105-0.319`
- thumb_tendon: `0.241-0.478`
- index: `0.681-0.961`
- middle: `0.304-0.718`
- ring: `0.370-0.772`
- pinky: `0.445-0.826`

### Current Interpretation
- The fitted trace is useful as the real-hand baseline.
- It should be compared against failed exact traces during sim-real identification.
- It is not proof that the trained policy has transferred; it is evidence about what command window currently works best on the real mechanism.

## Current Best Next Step

Use the paired artifacts:

- Failed sim-success traces, especially RealTunedWindow and PhysicsID exact traces.
- The current fitted replay preset `physics_id_rollout0_real_hand_fitted`.
- Real videos and telemetry logs from the same traces.

Then build a sim-real identification loop:

1. Replay the same exact traces in sim.
2. Modify contact geometry, palm support, friction, tendon stiffness/damping, and action-to-joint coupling.
3. Make failed real traces fail in sim in the same way.
4. Make the fitted real-hand trace score/look better than the failed traces.
5. Only then train another policy in the corrected simulator.
