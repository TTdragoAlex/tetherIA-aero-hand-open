#!/usr/bin/env python3
"""Smoke-test loading the TetherIA Aero Hand MuJoCo model.

This does not connect to the physical hand. It only verifies that MuJoCo can
parse the Menagerie XML model and step a few frames.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_XML = REPO_ROOT / "sim" / "mujoco_menagerie" / "tetheria_aero_hand_open" / "scene_right.xml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Load and step the TetherIA Aero Hand MuJoCo XML.")
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML)
    parser.add_argument("--steps", type=int, default=20)
    args = parser.parse_args()

    if not args.xml.exists():
        print(f"XML not found: {args.xml}")
        print("Clone mujoco_menagerie into sim/mujoco_menagerie first.")
        return 2

    try:
        import mujoco
    except ImportError:
        print("Python package 'mujoco' is not installed in this environment.")
        print("Install it with: sim/.venv/bin/python -m pip install mujoco")
        return 2

    model = mujoco.MjModel.from_xml_path(str(args.xml))
    data = mujoco.MjData(model)

    for _ in range(args.steps):
        mujoco.mj_step(model, data)

    print("MuJoCo Aero Hand XML loaded OK")
    print(f"xml: {args.xml}")
    print(f"nq={model.nq} nv={model.nv} nu={model.nu} nbody={model.nbody} ntendon={model.ntendon}")
    print(f"sim_time={data.time:.4f}s after {args.steps} steps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
