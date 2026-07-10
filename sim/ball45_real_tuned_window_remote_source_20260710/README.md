# Ball45 RealTunedWindow Remote Source Snapshot

This folder records the Ubuntu training-PC source files used to start the first
45 mm ball training series on 2026-07-10.

Remote source backup before editing:

```text
/home/hw/aero-hand-sim/backups/20260710_092528_ball45/
```

New environment:

```text
AeroBall45mmRotateZAxisHardware01RealTunedWindow
```

Training run:

```text
Run id: aero_ball45_real_tuned_window_fresh_20260710_093242
PID: 127699
Log: /home/hw/aero-hand-sim/runs/nohup_logs/aero_ball45_real_tuned_window_fresh_20260710_093242.log
Run dir: /home/hw/aero-hand-sim/logs/AeroBall45mmRotateZAxisHardware01RealTunedWindow-20260710-093244-aero_ball45_real_tuned_window_fresh_20260710_093242
Latest-run pointer: /home/hw/aero-hand-sim/runs/nohup_logs/latest_ball45_real_tuned_window_run.txt
```

Object details:

- Sphere radius: `0.0225 m`.
- Sphere diameter: `0.045 m`.
- Internal body/freejoint/geom/sensor names intentionally remain `cube` so the
  existing reward, randomization, rollout, trace, and export tooling still works.
- A small non-colliding marker dot is attached to the ball so rollout videos can
  show true spin instead of only object translation.

Changed files copied here:

- `rotate_z.py`
- `aero_hand_constants.py`
- `__init__.py`
- `manipulation_params.py`
- `reorientation_ball_45mm.xml`
- `scene_mjx_ball_45mm.xml`
