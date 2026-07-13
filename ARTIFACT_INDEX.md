# Artifact Index

This file is a plain-English map for the copied simulation videos, traces, and
logs. It is meant for readers who are new to the project and do not already know
which `rollout0.mp4` belongs to which experiment.

## Naming Rules

- Dates in folder names use `YYYYMMDD`.
- `rollout0.mp4`, `rollout1.mp4`, and `rollout2.mp4` are usually three sampled
  evaluation rollouts from the same training checkpoint.
- `_trace_` folders contain JSON command traces that can be replayed on the real
  hand with `scripts/replay_hardware01_u_trace_safe.py`.
- `u_trace.json` files use the real hardware order:
  `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`.
- `config.json` and `*.log` files document the training configuration and remote
  training log copied from the Ubuntu training PC.
- Some local file modification times are later than the run date because videos
  were copied from the training PC to the Mac after training completed.

## Current Best Real-Hand Replay

The best labeled real-hand open-loop replay is:

```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --run \
  --preset physics_id_rollout0_real_hand_fitted
```

This is not a trained closed-loop policy. It is a named replay preset for the
current best fitted exact trace:

- Source trace:
  `sim/hardware01_real_calibrated_physics_id_trace_20260708/hardware01_physics_id_rollout0_u_trace.json`
- Scale:
  `thumb_abd=0.90,thumb_flex=0.5,thumb_tendon=0.6,index=0.50,middle=0.7`
- Bias:
  `thumb_abd=-0.04,thumb_flex=-0.32,thumb_tendon=-0.14,index=0.34,middle=0.12,pinky=0.04`
- Dry-run command ranges:
  thumb_abd `0.326-0.864`, thumb_flex `0.105-0.319`,
  thumb_tendon `0.241-0.478`, index `0.681-0.961`,
  middle `0.304-0.718`, ring `0.370-0.772`, pinky `0.445-0.826`.

## Main Experiment Timeline

| Date | Folder | What It Is | Outcome |
| --- | --- | --- | --- |
| 2026-06-29 | `sim/actuator_diagnostics/` | Per-actuator sign/range videos from the original sim action space. | Helped identify action sign/order confusion. |
| 2026-07-03 | `sim/hardware01_action_diagnostics/` | Hardware-order `u=0..1` diagnostic videos for each channel. | Established the real-order channel convention used later. |
| 2026-07-06 | `sim/hardware01_randomized_20260706/` and `sim/hardware01_randomized_continue*_20260706/` | Early randomized hardware01 training runs. | Useful baselines, not final transfer candidates. |
| 2026-07-06 | `sim/hardware01_efficient_*_20260706/` | Efficient hardware01 policy variants. | Produced preserved baseline actor and videos. |
| 2026-07-06 | `sim/hardware01_exact_rollout_trace_20260706/` | Exact `u_real_order` traces and matching videos from the old efficient policy. | Exact trace replay became the main transfer-debug method. |
| 2026-07-07 | `sim/hardware01_real_calibrated_20260707/` | First real-calibrated training run. | Sim rotated the cube but was too jittery/bouncy for hardware. |
| 2026-07-07 | `sim/hardware01_real_calibrated_smooth_20260707/` | Smooth variant with action slew limiting and stronger smoothness costs. | Smoother, but often used thumb-index wedging. |
| 2026-07-07 | `sim/hardware01_real_calibrated_antitrap_20260707/` | Smooth plus anti-trap penalties. | Better in sim, but still cradle/pocket-like. |
| 2026-07-07 | `sim/hardware01_real_calibrated_antitrap_trace_20260707/` | Exact anti-trap traces exported after env smoothing. | Hardware replay was electrically safe but visually failed: thumb pushed cube off. |
| 2026-07-08 | `sim/physics_id_antitrap_rollout1_native_seeded_20260708/` | Seeded native MuJoCo physics sweep replaying anti-trap rollout 1. | Suggested thumb-dominant contact plus weak opposing support as a failure direction. |
| 2026-07-08 | `sim/physics_id_remote_source_20260708/` | Source snapshot and patch for the PhysicsID environment. | Documents the remote sim changes. |
| 2026-07-08 | `sim/hardware01_real_calibrated_physics_id_20260708/` | PhysicsID training videos/config/log. | Looked good in sim, but exact replay still pushed the cube off in reality. |
| 2026-07-08 | `sim/hardware01_real_calibrated_physics_id_trace_20260708/` | Exact PhysicsID traces exported after smoothing. | Source for the current best real-hand-fitted replay preset. |
| 2026-07-08/09 | `sim/real_tuned_window_remote_source_20260708/` | Source snapshot and patch for RealTunedWindow. | Documents training the operator-fitted command window into sim. |
| 2026-07-09 | `sim/hardware01_real_tuned_window_20260708/` | RealTunedWindow videos/config/log copied to the Mac. | Looked plausible in sim, but real replay still failed. |
| 2026-07-09 | `sim/hardware01_real_tuned_window_trace_20260708/` | Exact RealTunedWindow traces. | Dry-run passed; real replay failure confirmed sim-real mismatch. |
| 2026-07-10 | `sim/ball45_real_tuned_window_remote_source_20260710/` | Source snapshot for the new 45 mm ball training env. | Documents the 45 mm ball XML/env registration. |
| 2026-07-10 | `sim/ball45_real_tuned_window_20260710/` | First 45 mm ball training videos/config/log. | Completed cleanly, but videos are visually misleading because the full ball did not render clearly. |
| 2026-07-10 | `sim/ball45_real_tuned_window_visualfix_20260710/` | Regenerated 45 mm ball videos/log/XML from checkpoint `000157286400`. | Use this folder for review; it shows the full 45 mm orange ball plus black orientation marker. |
| 2026-07-10 | `sim/live_actor_export_ball45_real_tuned_window_000157286400/` | Live actor export for the 45 mm ball policy. | Blocked after two no-object current aborts and repeated clamp/release behavior. |
| 2026-07-10 | `sim/hand_observation_calibration_20260626.json` | Per-servo no-object current-vs-position baseline generated from the 2026-06-26 spring sweep. | Insufficient for coupled hand postures; do not use it to authorize the ball actor. |
| 2026-07-10 | `logs/coupled_current_baseline_20260710_160835.csv` | First no-object coupled-pose current record from fitted trace pose 0. | Passed below the collector's `1800 mA` soft threshold; use as the first sample for a coupled baseline. |
| 2026-07-10 | `logs/coupled_current_baseline_20260710_162258.csv` | Second no-object coupled-pose run: pose 0 repeated and source pose 12 added. | Both poses passed below the soft threshold; useful coverage of a different thumb/finger load distribution. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_095516.csv` | Four-pose no-object coupled-current run with eight settled readings per pose. | Quantifies normal held-current variation for source poses 0, 12, 24, and 36; use for the baseline's median/spread model. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_095924.csv` | Five-pose no-object coupled-current run with eight settled readings per pose. | Adds source pose 48; all held readings remained near 1 A and support the safe coupled baseline. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_100341.csv` | Six-pose no-object coupled-current run with eight settled readings per pose. | Adds source pose 60 and completes the first safe coupled-posture coverage set; use for offline baseline design only. |
| 2026-07-13 | `sim/hand_coupled_observation_calibration_20260713.json` | Guarded current median/spread distributions from the initial coupled-pose dataset. | Explicitly offline-only; a future controller must reject postures outside its `0.08` nearest-pose support radius. |
| 2026-07-13 | `sim/hand_coupled_observation_validation_20260713.json` | Leave-one-session-out current residual report for repeated coupled poses. | Validates temporal repeatability at measured poses only; do not interpret as interpolation or contact-detection validation. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_101750.csv` | Single new no-object coupled-pose probe at source step 72. | Completed safely and adds coverage; it requires a future repeat before temporal validation. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_102428.csv` | Single new no-object coupled-pose probe at source step 84. | Completed safely and adds coverage; it requires a future repeat before temporal validation. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_102644.csv` | Single new no-object coupled-pose probe at source step 96. | Completed safely; temporally validated by the later repeat session. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_102822.csv` | Single new no-object coupled-pose probe at source step 108. | Completed safely; temporally validated by the later repeat session. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_102911.csv` | Single new no-object coupled-pose probe at source step 120. | Completed safely; temporally validated by the later repeat session. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_102952.csv` | Second no-object session across source steps 60-120. | Provides repeat coverage for the second half of the fitted trace; all poses returned to rest. |
| 2026-07-13 | `sim/coupled_current_coverage_plan_20260713.json` | Planning-only ranking of unmeasured trace commands by baseline coverage gap. | Uses transformed targets as an estimate; each candidate still needs a guarded collector dry run and hardware safety limits. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_103533.csv` | Planned no-object coverage probe at source step 45. | Completed safely with a full settled/return record. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_103625.csv` | Planned no-object coverage probe at source step 94. | Completed safely despite one recovered SDK current-read timeout; full CSV record and post-run rest telemetry are valid. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_103735.csv` | Planned no-object coverage probe at source step 32. | Completed safely with a full settled/return record. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_103805.csv` | Planned no-object coverage probe at source step 69. | Completed safely with a full settled/return record. |
| 2026-07-13 | `sim/hand_coupled_current_model_benchmark_20260713.json` | Source-pose holdout comparison of nearest-pose and ridge no-object current models. | Offline-only rejection of current global models; retain guarded local support. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_104230.csv` | Planned no-object coverage probe at source step 117. | Completed safely with a full settled/return record. |
| 2026-07-13 | `logs/coupled_current_baseline_20260713_104304.csv` | Planned no-object coverage probe at source step 122. | Completed safely with a full settled/return record. |

## How To Interpret A `rollout*.mp4`

Do not compare `rollout0.mp4` files across folders as if they are the same
policy. The folder name is the experiment identity. For example:

- `sim/hardware01_real_calibrated_20260707/rollout0.mp4` is the first sampled
  video from the first real-calibrated run.
- `sim/hardware01_real_calibrated_physics_id_20260708/rollout0.mp4` is the first
  sampled video from the later PhysicsID run.

Within one folder, `rollout0`, `rollout1`, and `rollout2` are usually the three
rendered evaluation episodes from the same checkpoint. They are useful for
checking whether a policy has consistent behavior or only succeeds in one seed.

## Current Conclusion

The simulator can now produce many policies that look plausible in video, but
those policies repeatedly fail on the real hand by trapping, caging, or pushing
the cube away. The next main work is therefore not another reward-only training
variant. The next main work is sim-real identification: replay exact traces in
sim and tune geometry/contact/compliance until the simulator reproduces the same
failure modes seen on the real hand.

The ball actor's first live test exposed two separate issues. Feeding its own
commands plus a fixed force value removed feedback, while the follow-up
single-servo current baseline underestimated spring load when several fingers
were active together. The actor is now blocked from hardware motion pending a
coupled-pose current calibration dataset.
