# AGENTS.md

## Repo Layout
- `scripts/`: Mac-side hand control, replay, live policy, current profiling, mapping audits.
- `sim/`: Copied training videos, actor exports, exact policy traces, sim diagnostics.
- `logs/`: CSV logs from real-hand tests and replay/live-policy runs.
- `firmware-platformio/`: ESP32/PlatformIO firmware project for the hand controller.
- `aero_hand_calibration.json`: Current Mac-side raw rest/open calibration.
- Ubuntu training PC source lives outside this repo at `hw@192.168.9.63:/home/hw/aero-hand-sim`.

## Setup
- Mac project root: `/Users/alextang/Documents/Robot Hand`.
- Python venv: `./.venv/bin/python`.
- Ubuntu PC SSH: `ssh hw@192.168.9.63`; enter the operator-provided password when prompted.
- Physical hand command order is `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`.
- Original sim order is `[index, middle, ring, pinky, thumb_abd, thumb_flex, thumb_tendon]`; never assume these orders match.

## Common Commands
- List serial ports: `./.venv/bin/python scripts/list_ports.py`.
- Open GUI: `./launch_gui.sh` or `open "Open Aero Hand GUI.command"`.
- Compile firmware: `cd firmware-platformio && ../.venv/bin/platformio run`.
- No-cube current sweep: `./.venv/bin/python scripts/channel_friction_sweep.py --run --channels index,middle --start 0.0 --stop 0.90 --step 0.05 --hold 0.35 --max-step-delta 0.02`.
- Safe exact trace replay: `./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py --run --trace sim/hardware01_exact_rollout_trace_20260706/hardware01_rollout0_u_trace.json --steps 120 --playback-scale 1.00 --max-step-delta 0.08 --sample-every 5`.

## Hard Constraints
- Do not move the real hand unless the user says it is connected, mounted, and clear.
- Tell the user when the hand is no longer needed so it can be disconnected.
- Keep safety aborts unless explicitly testing safety itself: current default `4000 mA`, temp default `60 C`.
- Do not overwrite old sim environments or checkpoints; add variants and copy artifacts.
- The training PC repo is not git-controlled; create timestamped backups before editing remote source.
- Do not double-apply old replay calibration to new `RealCalibrated` traces; scale/bias should be trained into that env.

## Done Means
- Code or env changes compile/smoke-test.
- Real-hand tests log commands, positions, currents, temperatures, and abort reasons.
- Sim artifacts copied back to `sim/` with clear names.
- The next operator can reproduce the last command from docs/logs.
