#!/usr/bin/env python3
"""Benchmark offline no-object current predictors by held-out source posture.

The benchmark compares a guarded nearest-pose lookup with regularized linear
full-posture models. It is a model-selection aid only: no result authorizes
live actor control or object-contact inference.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]


def ridge_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray, alpha: float) -> np.ndarray:
    """Fit standardized ridge regression with an unpenalized intercept."""
    mean = x_train.mean(axis=0)
    scale = np.maximum(x_train.std(axis=0), 1e-4)
    design = np.column_stack((np.ones(len(x_train)), (x_train - mean) / scale))
    test = np.concatenate(([1.0], (x_test - mean) / scale))
    penalty = np.eye(design.shape[1]) * alpha
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ y_train)
    return test @ coefficients


def summary(errors: np.ndarray) -> dict[str, list[float]]:
    absolute = np.abs(errors)
    return {
        "median_absolute_ma": np.median(absolute, axis=0).round(3).tolist(),
        "p95_absolute_ma": np.percentile(absolute, 95, axis=0).round(3).tolist(),
        "max_absolute_ma": np.max(absolute, axis=0).round(3).tolist(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate offline coupled current baseline models by leave-one-source-pose-out error.")
    parser.add_argument("--calibration", type=Path, default=REPO_ROOT / "sim" / "hand_coupled_observation_calibration_20260713.json")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "sim" / "hand_coupled_current_model_benchmark_20260713.json")
    parser.add_argument("--ridge-alphas", default="0.001,0.01,0.1,1,10")
    args = parser.parse_args()

    calibration = json.loads(args.calibration.read_text())
    samples = calibration["samples"]
    if len(samples) < 3:
        raise ValueError("At least three source postures are required")
    x = np.asarray([sample["position_median"] for sample in samples], dtype=np.float64)
    y = np.asarray([sample["current_baseline_ma"] for sample in samples], dtype=np.float64)
    alphas = [float(value) for value in args.ridge_alphas.split(",")]
    if any(value <= 0.0 for value in alphas):
        raise ValueError("--ridge-alphas must be positive")

    models: dict[str, dict[str, object]] = {}
    nearest_errors = []
    for held_out in range(len(samples)):
        train_indices = [idx for idx in range(len(samples)) if idx != held_out]
        distances = np.linalg.norm(x[train_indices] - x[held_out], axis=1)
        nearest_errors.append(y[train_indices[int(np.argmin(distances))]] - y[held_out])
    models["nearest_pose"] = summary(np.asarray(nearest_errors))

    for alpha in alphas:
        errors = []
        for held_out in range(len(samples)):
            train_indices = [idx for idx in range(len(samples)) if idx != held_out]
            prediction = ridge_predict(x[train_indices], y[train_indices], x[held_out], alpha)
            errors.append(prediction - y[held_out])
        models[f"ridge_alpha_{alpha:g}"] = summary(np.asarray(errors))

    output = {
        "format": "aero_hand_coupled_current_model_benchmark_v1",
        "status": "offline_only",
        "method": "leave_one_source_pose_out",
        "calibration": str(args.calibration.relative_to(REPO_ROOT)) if args.calibration.is_relative_to(REPO_ROOT) else str(args.calibration),
        "channel_order": calibration["channel_order"],
        "source_steps": [sample["source_step"] for sample in samples],
        "models": models,
        "notes": [
            "Each held-out source posture is predicted from all other source postures.",
            "This measures no-object interpolation/extrapolation error at observed poses only.",
            "The benchmark does not authorize live deployment or establish object-contact thresholds.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Wrote {args.output}")
    for name, result in models.items():
        print(f"{name}: median={result['median_absolute_ma']} max={result['max_absolute_ma']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
