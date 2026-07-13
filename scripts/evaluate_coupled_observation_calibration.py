#!/usr/bin/env python3
"""Evaluate coupled no-object current drift with leave-one-session-out holds.

For a source pose observed in at least two collector logs, predict one session's
settled-current median from the other sessions at the same source pose. This is
an offline stability check, not a contact-classifier evaluation.
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


def session_medians(paths: list[Path]) -> dict[int, dict[str, np.ndarray]]:
    grouped: dict[int, dict[str, list[np.ndarray]]] = defaultdict(lambda: defaultdict(list))
    for path in paths:
        with path.open(newline="") as file:
            for row in csv.DictReader(file):
                if row.get("event") not in {"hold_sample", "sample"}:
                    continue
                current = np.asarray(
                    [float(row[f"curr_ma_{idx}_{name}"]) for idx, name in enumerate(CHANNEL_NAMES)], dtype=np.float64
                )
                grouped[int(row["source_step"])][path.name].append(current)
    return {
        step: {name: np.median(values, axis=0) for name, values in sessions.items()}
        for step, sessions in grouped.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Leave-one-session-out validation for coupled no-object current data.")
    parser.add_argument("--logs", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "sim" / "hand_coupled_observation_validation_20260713.json",
    )
    args = parser.parse_args()

    medians = session_medians(args.logs)
    cases = []
    for source_step, sessions in sorted(medians.items()):
        names = sorted(sessions)
        if len(names) < 2:
            continue
        for held_out in names:
            training = np.stack([sessions[name] for name in names if name != held_out])
            expected = np.median(training, axis=0)
            residual = sessions[held_out] - expected
            cases.append(
                {
                    "source_step": source_step,
                    "held_out_log": held_out,
                    "training_logs": [name for name in names if name != held_out],
                    "residual_ma": residual.round(3).tolist(),
                    "absolute_residual_ma": np.abs(residual).round(3).tolist(),
                }
            )
    if not cases:
        raise ValueError("Need at least two logs with an overlapping source pose")

    absolute = np.asarray([case["absolute_residual_ma"] for case in cases], dtype=np.float64)
    output = {
        "format": "aero_hand_coupled_observation_validation_v1",
        "status": "offline_only",
        "source_logs": [str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path) for path in args.logs],
        "channel_order": CHANNEL_NAMES,
        "method": "leave_one_session_out_same_source_pose_median",
        "case_count": len(cases),
        "unvalidated_source_steps": [step for step, sessions in sorted(medians.items()) if len(sessions) < 2],
        "absolute_residual_summary_ma": {
            "median": np.median(absolute, axis=0).round(3).tolist(),
            "p95": np.percentile(absolute, 95, axis=0).round(3).tolist(),
            "max": np.max(absolute, axis=0).round(3).tolist(),
        },
        "cases": cases,
        "notes": [
            "Only tests repeated source poses; it does not validate interpolation between poses or object-contact detection.",
            "Use the per-channel residual distribution to set a future sustained-contact threshold, never a global raw-current threshold.",
            "Source steps with one session are retained in the calibration but cannot receive temporal holdout validation.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    summary = output["absolute_residual_summary_ma"]
    print(f"Wrote {args.output}")
    print(f"holdout cases: {len(cases)}; unvalidated source steps: {output['unvalidated_source_steps']}")
    print(f"per-channel absolute residual median (mA): {summary['median']}")
    print(f"per-channel absolute residual max (mA): {summary['max']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
