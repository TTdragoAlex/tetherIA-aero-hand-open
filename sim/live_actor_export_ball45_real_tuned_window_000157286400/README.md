# 45 mm Ball Live Actor Export

Exported from checkpoint `000157286400` of
`AeroBall45mmRotateZAxisHardware01RealTunedWindow`.

Files:

- `actor_policy.npz`: NumPy actor weights and observation normalization.
- `actor_policy_metadata.json`: command order, observation order, source run,
  and recommended live-test settings.

## Hardware Status: Blocked

Two no-object tests on 2026-07-10 hit the `4000 mA` safety abort. The motion
was a repeated clamp/release, not the simulated rolling behavior. Do not run
this actor on the physical hand; the controller now refuses `--run` for this
export unless a future, deliberate diagnostic supplies
`--allow-unapproved-policy`.

The cause is observable in the test logs. At the actor's mean posture, the
index drew about `3.3-3.4 A` with no object, while the single-servo sweep
baseline predicted roughly `1.0 A`. The current residual therefore appeared as
near-maximum object contact to the actor and drove it into an index/ring clamp
followed by thumb-tendon closure.

The next step is a safe, coupled-pose no-object calibration dataset inside a
known low-current command window. That dataset must model each current as a
function of the full seven-servo posture, not one channel at a time. Only then
should we retry a live actor or use the ball.

The existing single-servo calibration can still be regenerated after a spring,
tendon, or servo change, but it is not sufficient to authorize this actor:

```bash
./.venv/bin/python scripts/build_observation_calibration.py \
  --sweep logs/channel_friction_sweep_YYYYMMDD_HHMMSS.csv
```
