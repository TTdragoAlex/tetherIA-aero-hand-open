#!/usr/bin/env python3
"""Build a guarded no-object current baseline from coupled-pose collector logs.

This is intentionally an offline artifact. Six sparse seven-servo poses cannot
justify extrapolating a current/contact model across live-policy motion. The
output therefore stores observed posture/current distributions and a maximum
nearest-pose distance for a future controller to enforce explicitly.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402


def read_samples(paths: list[Path]) -> dict[int, list[tuple[np.ndarray, np.ndarray]]]:
    """Read settled no-object telemetry, grouped by source trace step."""
    grouped: dict[int, list[tuple[np.ndarray, np.ndarray]]] = defaultdict(list)
    for path in paths:
        with path.open(newline="") as file:
            rows = csv.DictReader(file)
            for row in rows:
                if row.get("event") not in {"hold_sample", "sample"}:
                    continue
                source_step = int(row["source_step"])
                position = np.asarray(
                    [float(row[f"pos_{idx}_{name}"]) for idx, name in enumerate(CHANNEL_NAMES)], dtype=np.float64
                )
                current = np.asarray(
                    [float(row[f"curr_ma_{idx}_{name}"]) for idx, name in enumerate(CHANNEL_NAMES)], dtype=np.float64
                )
                grouped[source_step].append((position, current))
    if not grouped:
        raise ValueError("No settled hold_sample/sample telemetry was found")
    return grouped


def build_sample(source_step: int, rows: list[tuple[np.ndarray, np.ndarray]]) -> dict[str, object]:
    positions = np.stack([position for position, _ in rows])
    currents = np.stack([current for _, current in rows])
    return {
        "source_step": source_step,
        "sample_count": len(rows),
        "position_median": np.median(positions, axis=0).round(6).tolist(),
        "position_std": np.std(positions, axis=0).round(3).tolist(),
        "current_baseline_ma": np.median(currents, axis=0).round(3).tolist(),
        "current_std_ma": np.std(currents, axis=0).round(3).tolist(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a guarded coupled-posture no-object current calibration.")
    parser.add_argument("--logs", type=Path, nargs="+", required=True, help="Collector CSV logs containing settled hold samples.")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "sim" / "hand_coupled_observation_calibration_20260713.json",
    )
    parser.add_argument(
        "--max-nearest-distance",
        type=float,
        default=0.08,
        help="Maximum Euclidean normalized-position distance that a future controller may treat as supported.",
    )
    args = parser.parse_args()
    if not 0.0 < args.max_nearest_distance <= 1.0:
        raise ValueError("--max-nearest-distance must be in (0, 1]")

    grouped = read_samples(args.logs)
    samples = [build_sample(step, grouped[step]) for step in sorted(grouped)]
    positions = np.asarray([sample["position_median"] for sample in samples], dtype=np.float64)
    distances = np.linalg.norm(positions[:, None, :] - positions[None, :, :], axis=-1)
    np.fill_diagonal(distances, np.nan)
    nearest = np.nanmin(distances, axis=1) if len(samples) > 1 else np.asarray([np.nan])

    output = {
        "format": "aero_hand_coupled_observation_calibration_v1",
        "method": "guarded_nearest_pose_v1",
        "status": "offline_only",
        "source_logs": [str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path) for path in args.logs],
        "channel_order": CHANNEL_NAMES,
        "position_feature": "measured_get_pos_normalized",
        "max_nearest_distance": args.max_nearest_distance,
        "samples": samples,
        "coverage": {
            "unique_source_steps": [sample["source_step"] for sample in samples],
            "nearest_sample_distance_min": round(float(np.nanmin(nearest)), 6) if len(samples) > 1 else None,
            "nearest_sample_distance_median": round(float(np.nanmedian(nearest)), 6) if len(samples) > 1 else None,
            "nearest_sample_distance_max": round(float(np.nanmax(nearest)), 6) if len(samples) > 1 else None,
        },
        "notes": [
            "Built only from no-object settled telemetry in coupled seven-servo postures.",
            "Each sample stores a per-channel median and standard deviation, not a physical force calibration.",
            "A future controller must reject positions farther than max_nearest_distance from every sample.",
            "This artifact is offline_only until independent holdout validation and explicit hardware approval.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")

    print(f"Wrote {args.output}")
    print(f"samples: {len(samples)}; source steps: {output['coverage']['unique_source_steps']}")
    print(
        "nearest-pose spacing (min/median/max): "
        f"{output['coverage']['nearest_sample_distance_min']}/"
        f"{output['coverage']['nearest_sample_distance_median']}/"
        f"{output['coverage']['nearest_sample_distance_max']}"
    )
    print(f"future-controller support radius: {args.max_nearest_distance:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
