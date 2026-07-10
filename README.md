# TetherIA Aero Hand Open

Mac-side control, firmware notes, simulation artifacts, and sim-to-real transfer
work for a TetherIA/Aero robot hand cube-rotation project.

Official TetherIA documentation:
[docs.tetheria.ai/docs](https://docs.tetheria.ai/docs)

Use the official docs for vendor SDK, hardware, and firmware background. This
repo documents the local safety wrappers, calibration work, replay tools,
simulation artifacts, and current transfer results.




https://github.com/user-attachments/assets/1117ed57-efa8-4b72-aa60-6e55b14517da



https://github.com/user-attachments/assets/8321e103-9bb9-4f42-b866-c4b3799f2c9f






## Current Status

The physical hand works: the servos move, homing/calibration is usable, GUI
control works, and exact simulation traces can be replayed on hardware. The hand is able to perform the cube rotation task to a very well extent.

The current best real-hand result is a fitted open-loop replay preset, not a
general closed-loop policy:

```bash
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --preset physics_id_rollout0_real_hand_fitted
```

A separate 45 mm ball training series started on 2026-07-10 to test whether a
round, grippy object avoids the cube's trapping/ejection failure modes.
Review the corrected videos in `sim/ball45_real_tuned_window_visualfix_20260710/`;
the first copied ball videos made the ball look like a tiny dot because only
the orientation marker rendered clearly.

The 45 mm ball actor now has an experimental live-observation bridge: it uses
measured servo positions plus current above a recorded no-object spring/friction
baseline. It has passed offline checks but still requires a no-object hardware
test before the ball is introduced. See the actor artifact README and RUNBOOK.

## Safety

- Do not move the physical hand unless it is connected, mounted, and clear.
- Hardware-moving scripts dry-run by default. Add `--run` only when ready.
- Current abort at `4000 mA` unless explicitly testing safety itself.
- Temperature abort at `65 C` unless explicitly testing safety itself (Feetech lists the motors can go up 85 C).
- Physical command order is:
  `[thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky]`

## Quick Start

These steps are for running the current replay/preset tools on the same
physical hand. They do not install the full Ubuntu training stack.

```bash
git clone https://github.com/TTdragoAlex/tetherIA-aero-hand-open.git
cd tetherIA-aero-hand-open

python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```

List serial ports:

```bash
./.venv/bin/python scripts/list_ports.py
```

Dry-run the current fitted replay:

```bash
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --preset physics_id_rollout0_real_hand_fitted
```

Run it only when the hand is connected, mounted, and clear:

```bash
./.venv/bin/python scripts/replay_hardware01_u_trace_safe.py \
  --run \
  --preset physics_id_rollout0_real_hand_fitted
```

If auto-detect does not find the hand, pass a port explicitly.

macOS usually uses `/dev/cu.usbmodemXXXX`:

```bash
--port /dev/cu.usbmodem1101
```

Linux usually uses `/dev/ttyACM0` or `/dev/ttyUSB0`. Linux users may also need:

```bash
sudo usermod -aG dialout "$USER"
```

Log out and back in after changing serial group membership.

## What The Preset Reproduces

`physics_id_rollout0_real_hand_fitted` replays a fitted command trace that has
worked best so far on the real hand. It depends on the same hardware setup,
mounting, springs, tendon tension, calibration, cube placement, and roughly a
`5.4 cm` cube. A different hand or setup may need recalibration and retuning.

This preset is useful as a baseline for debugging sim-real mismatch. It is not
yet a deployable autonomous cube-rotation policy.

## Repository Map

- `scripts/`: Mac-side hand control, replay, telemetry, policy, sweep, and audit
  tools.
- `sim/`: Copied training videos, exact traces, actor exports, diagnostics, and
  remote source snapshots.
- `sim/hand_observation_calibration_20260626.json`: no-object servo-current
  baseline used by the experimental ball live-observation bridge.
- `logs/`: CSV logs from real-hand tests and replay/live-policy runs.
- `firmware-platformio/`: ESP32/PlatformIO firmware project.
- `aero_hand_calibration.json`: current Mac-side raw rest/open calibration.

The Ubuntu training source lives outside this repo:

```text
hw@192.168.9.63:/home/hw/aero-hand-sim
```

That remote source is not git-controlled. Create timestamped backups before
editing it.

## Where To Read More

- [RUNBOOK.md](RUNBOOK.md): operator commands for hardware tests, training,
  artifact copying, and common issues.
- [PROJECT_STATE.md](PROJECT_STATE.md): current state, what works, what is
  broken, and important files.
- [TODO.md](TODO.md): next engineering tasks.
- [ARTIFACT_INDEX.md](ARTIFACT_INDEX.md): plain-English guide to videos, traces,
  folders, dates, and rollout numbering.
- [PROBLEM_FIX_LOG.md](PROBLEM_FIX_LOG.md): chronological history of problems,
  attempts, fixes, and lessons learned.
- [TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md): command order, action-space
  facts, replay safety behavior, fitted preset details, and local technical
  changes.
- [DECISIONS.md](DECISIONS.md): decisions that should not be rediscovered.

## Next Work

Do not treat another sim-only successful policy as progress by itself. First
validate the measured-position/current observation bridge with no object; then
use the result to guide sim-real identification of contact, geometry,
compliance, friction, and support.
