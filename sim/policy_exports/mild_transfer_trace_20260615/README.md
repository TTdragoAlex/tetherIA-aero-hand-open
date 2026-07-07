# mild_transfer Policy Trace Export

This folder contains the selected `mild_transfer` sim policy exported into a
plain CSV trace for later hardware replay.

## Files

- `mild_transfer_trace.csv`: 500 policy steps, 25 seconds at `dt=0.05`.
- `mild_transfer_trace_metadata.json`: checkpoint, channel mapping, rest pose,
  and export settings.

## Mapping

Sim actuator order:

```text
index, middle, ring, pinky, thumb_abd, thumb_tendon1, thumb_tendon2
```

Physical raw actuator order:

```text
thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky
```

The conservative hardware target is:

```text
raw_rest + playback_scale * max(0, mapped_sim_action)
```

The default playback scale is `0.25`.

## Dry Runs

No hardware connection:

```bash
./.venv/bin/python scripts/replay_policy_trace_safe.py
```

First very short hardware rehearsal later, after Codex explicitly says to
connect the hand:

```bash
./.venv/bin/python scripts/replay_policy_trace_safe.py --run --max-steps 50 --playback-scale 0.10
```

Do not run hardware replay until the hand is mounted, powered safely, clear of
obstacles, and the emergency power cutoff is reachable.
