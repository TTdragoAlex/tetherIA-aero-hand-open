# 45 mm Ball Live Actor Export

Exported from checkpoint `000157286400` of
`AeroBall45mmRotateZAxisHardware01RealTunedWindow`.

Files:

- `actor_policy.npz`: NumPy actor weights and observation normalization.
- `actor_policy_metadata.json`: command order, observation order, source run,
  and recommended live-test settings.

## First Hardware Test

This is a no-object controller-integration test, not a ball test. It starts at
the actor's trained mean posture, uses physical `GET_POS`, and subtracts the
recorded no-object spring/friction current before producing the actor's force
input. The initial ramp and every control step retain the `4000 mA` and `65 C`
abort checks.

```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python scripts/live_policy_control.py \
  --run \
  --policy sim/live_actor_export_ball45_real_tuned_window_000157286400/actor_policy.npz \
  --steps 60 \
  --rate 10 \
  --playback-scale 1.0 \
  --action-mode hardware01 \
  --obs-mode hardware01 \
  --obs-input-space raw \
  --position-obs-source get_pos \
  --hardware01-initial-u policy_mean \
  --force-obs-source calibrated_current \
  --observation-calibration sim/hand_observation_calibration_20260626.json \
  --max-step-delta all=0.03 \
  --abort-current 4000 \
  --abort-temp 65 \
  --sample-every 5
```

Do not add the ball until this is smooth and electrically safe. The baseline
comes from `logs/channel_friction_sweep_20260626_105220.csv`; it removes
first-order spring/friction preload but is not a physical contact-force
calibration. In particular, thumb-flex baseline data above `u≈0.17` is held at
the protected sweep endpoint, so inspect thumb-flex current closely.

To regenerate the calibration after a spring, tendon, or servo change:

```bash
./.venv/bin/python scripts/build_observation_calibration.py \
  --sweep logs/channel_friction_sweep_YYYYMMDD_HHMMSS.csv
```
