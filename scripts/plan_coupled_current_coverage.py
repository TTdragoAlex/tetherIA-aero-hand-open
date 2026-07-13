#!/usr/bin/env python3
"""Plan informative no-object current probes from a guarded calibration.

The planner treats transformed trace targets as an approximation of measured
GET_POS. It only ranks candidates; the collector's existing current/temperature
limits remain responsible for hardware safety.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from replay_hardware01_u_trace_safe import PRESETS, load_trace, parse_channel_values, scale_target  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank trace poses that improve guarded current-baseline coverage.")
    parser.add_argument("--preset", choices=tuple(PRESETS), default="physics_id_rollout0_real_hand_fitted")
    parser.add_argument("--calibration", type=Path, default=REPO_ROOT / "sim" / "hand_coupled_observation_calibration_20260713.json")
    parser.add_argument("--count", type=int, default=8, help="Number of greedy farthest-point candidates to return.")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "sim" / "coupled_current_coverage_plan_20260713.json")
    args = parser.parse_args()
    if args.count < 1:
        raise ValueError("--count must be >= 1")

    calibration = json.loads(args.calibration.read_text())
    measured_steps = {int(sample["source_step"]) for sample in calibration["samples"]}
    support = float(calibration["max_nearest_distance"])
    reference = np.asarray([sample["position_median"] for sample in calibration["samples"]], dtype=np.float64)

    preset = PRESETS[args.preset]
    scale = parse_channel_values(str(preset["channel_scale"]), default=1.0)
    bias = parse_channel_values(str(preset["channel_bias"]), default=0.0)
    candidates = []
    for row in load_trace(preset["trace"]):
        step = int(row["step"])
        if step in measured_steps:
            continue
        target = np.asarray(scale_target(row["target"], float(preset["playback_scale"]), 0.5, scale, bias), dtype=np.float64)
        candidates.append((step, target))

    selected = []
    for _ in range(min(args.count, len(candidates))):
        distances = [float(np.linalg.norm(reference - target, axis=1).min()) for _, target in candidates]
        index = int(np.argmax(distances))
        step, target = candidates.pop(index)
        selected.append({"source_step": step, "estimated_target": target.round(6).tolist(), "distance_before_selection": round(distances[index], 6)})
        reference = np.vstack((reference, target))

    output = {
        "format": "aero_hand_coupled_current_coverage_plan_v1",
        "status": "planning_only",
        "calibration": str(args.calibration.relative_to(REPO_ROOT)) if args.calibration.is_relative_to(REPO_ROOT) else str(args.calibration),
        "support_radius": support,
        "method": "greedy_farthest_point_on_transformed_trace_targets",
        "limitations": [
            "Trace targets approximate, but do not replace, measured GET_POS.",
            "Candidates require normal collector dry-run and safety limits before hardware use.",
        ],
        "candidates": selected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Wrote {args.output}")
    for candidate in selected:
        print(
            f"step={candidate['source_step']:3d} distance={candidate['distance_before_selection']:.3f} "
            f"target={candidate['estimated_target']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
