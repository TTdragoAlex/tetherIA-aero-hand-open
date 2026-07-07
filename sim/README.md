# Aero Hand Sim Workspace

This directory is for MuJoCo / MuJoCo Playground work. It is intentionally
separate from the main `.venv` used for physical hand control.

## Goal

Start with sim-only validation before connecting anything to the physical hand:

1. Create a separate Python 3.12 sim environment.
2. Clone the MuJoCo Menagerie model and MuJoCo Playground code.
3. Verify the TetherIA Aero Hand XML loads locally.
4. Run or inspect the `AeroCubeRotateZAxis` environment.
5. Map sim tendon/action channels to the physical-hand Python API.
6. Only later, replay very conservative policy outputs on hardware with current/temp aborts.

## Local Mac Expectation

This Mac can be useful for:

- Loading and inspecting the MuJoCo model.
- Rendering or stepping small simulations.
- Inspecting actions and observations.
- Building the sim-to-real adapter.

Serious RL training will probably be better on an NVIDIA GPU machine or cloud
runtime because MuJoCo Playground recommends JAX/CUDA for training speed.

## Setup Sketch

From the repo root:

```bash
/opt/homebrew/bin/python3.12 -m venv sim/.venv
sim/.venv/bin/python -m pip install --upgrade pip
sim/.venv/bin/python -m pip install mujoco
git clone https://github.com/google-deepmind/mujoco_menagerie.git sim/mujoco_menagerie
git clone https://github.com/google-deepmind/mujoco_playground.git sim/mujoco_playground
```

Then smoke-test the hand XML:

```bash
sim/.venv/bin/python scripts/sim_load_aero_hand.py
```

## Hand Connection

Keep the physical hand disconnected for all sim setup and training work. It is
only needed later for carefully gated sim-to-real playback tests.
