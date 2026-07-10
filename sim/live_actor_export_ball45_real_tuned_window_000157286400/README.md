# 45 mm Ball Live Actor Export

Exported from checkpoint `000157286400` of
`AeroBall45mmRotateZAxisHardware01RealTunedWindow`.

Files:

- `actor_policy.npz`: NumPy actor weights and observation normalization.
- `actor_policy_metadata.json`: command order, observation order, source run,
  and recommended live-test settings.

First hardware test should be no-cube, low scale:

```bash
cd "/Users/alextang/Documents/Robot Hand"
./.venv/bin/python scripts/live_policy_control.py \
  --run \
  --policy sim/live_actor_export_ball45_real_tuned_window_000157286400/actor_policy.npz \
  --steps 60 \
  --rate 10 \
  --playback-scale 0.05 \
  --action-mode hardware01 \
  --obs-mode hardware01 \
  --obs-input-space raw \
  --position-obs-source command \
  --hardware01-initial-u rest \
  --current-scale-ma 4000 \
  --use-signed-current \
  --force-obs-source policy_mean \
  --default-max-step-delta 0.03 \
  --abort-current 4000 \
  --abort-temp 65 \
  --sample-every 5
```

Stop if the hand looks jerky, clamps hard, or current rises unexpectedly.
