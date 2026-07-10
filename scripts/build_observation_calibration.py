#!/usr/bin/env python3
"""Build a real-current observation calibration from a no-object servo sweep.

The output stores one signed current-vs-position baseline curve per physical
servo. Live policy control subtracts this curve before treating remaining
current as likely object contact load.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402


def build_channel_curve(rows: list[dict[str, str]], channel_idx: int, extend_to: float) -> dict[str, object]:
    name = CHANNEL_NAMES[channel_idx]
    samples: list[tuple[float, float]] = []
    for row in rows:
        if row.get("phase") != "hold" or row.get("event") != "ok":
            continue
        if int(row["channel"]) != channel_idx:
            continue
        samples.append((float(row[f"pos_{channel_idx}_{name}"]), float(row[f"curr_ma_{channel_idx}_{name}"])))
    if len(samples) < 2:
        raise ValueError(f"Sweep does not have at least two usable samples for {name}")

    # Servo telemetry has a little repeat noise. Keep the last value for a
    # repeated position, then require an increasing interpolation grid.
    by_position: dict[float, float] = {}
    for position, current in samples:
        by_position[round(position, 6)] = current
    points = sorted(by_position.items())
    if len(points) < 2:
        raise ValueError(f"Sweep positions for {name} are not usable")
    if extend_to > points[-1][0]:
        # Some protected sweeps stop early (notably thumb flex). A held endpoint
        # avoids treating known no-object spring preload beyond that point as ball
        # contact. This is intentionally marked in the output for later upgrade.
        points.append((extend_to, points[-1][1]))
    return {
        "name": name,
        "position": [round(position, 6) for position, _ in points],
        "current_baseline_ma": [round(current, 3) for _, current in points],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build no-object current baseline calibration from a channel friction sweep.")
    parser.add_argument("--sweep", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "sim" / "hand_observation_calibration_20260626.json",
    )
    parser.add_argument(
        "--residual-scale-ma",
        type=float,
        default=400.0,
        help="Current residual that maps to tanh(1) before actor observation normalization.",
    )
    parser.add_argument(
        "--extend-last-to",
        type=float,
        default=1.0,
        help="Hold each last measured baseline current out to this normalized position.",
    )
    args = parser.parse_args()
    if args.residual_scale_ma <= 0.0:
        raise ValueError("--residual-scale-ma must be positive")
    if not 0.0 < args.extend_last_to <= 1.0:
        raise ValueError("--extend-last-to must be in (0, 1]")

    with args.sweep.open(newline="") as file:
        rows = list(csv.DictReader(file))
    calibration = {
        "format": "aero_hand_observation_calibration_v1",
        "source_sweep": str(args.sweep.relative_to(REPO_ROOT)) if args.sweep.is_relative_to(REPO_ROOT) else str(args.sweep),
        "channel_order": CHANNEL_NAMES,
        "residual_scale_ma": args.residual_scale_ma,
        "hold_last_baseline_to": args.extend_last_to,
        "channels": [build_channel_curve(rows, idx, args.extend_last_to) for idx in range(len(CHANNEL_NAMES))],
        "notes": [
            "Signed current baseline from a no-object one-channel sweep.",
            "Live control adds tanh((current - baseline(position)) / residual_scale_ma) to the actor force mean.",
            "This removes first-order spring/friction preload; it is not a physical force calibration.",
            "Sweep endpoints are held to hold_last_baseline_to when protected sweeps stop early.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(calibration, indent=2) + "\n")
    print(f"Wrote {args.output}")
    for channel in calibration["channels"]:
        print(f"{channel['name']}: {len(channel['position'])} points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
