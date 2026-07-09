#!/usr/bin/env python3
"""Summarize current bottlenecks from policy replay CSV logs."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
import re


def servo_name_from_current_col(column: str) -> tuple[int, str]:
    match = re.match(r"curr_ma_(\d+)_(.+)", column)
    if not match:
        raise ValueError(f"Not a current column: {column}")
    return int(match.group(1)), match.group(2)


def load_rows(paths: list[Path]) -> list[tuple[Path, dict[str, str]]]:
    rows: list[tuple[Path, dict[str, str]]] = []
    for path in paths:
        with path.open(newline="") as file:
            for row in csv.DictReader(file):
                rows.append((path, row))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Aero hand replay logs for current bottlenecks.")
    parser.add_argument("logs", nargs="*", type=Path, help="CSV logs to analyze. Defaults to latest 20 replay logs.")
    parser.add_argument("--latest", type=int, default=20, help="How many latest logs to use when no logs are given.")
    parser.add_argument("--spike-threshold", type=float, default=1500.0, help="Current threshold for top spike details.")
    parser.add_argument("--bin-width", type=float, default=0.1, help="Target-position bin width for per-servo summaries.")
    parser.add_argument("--guard-current", type=float, default=4000.0, help="Current safety guard used for pass/fail summary.")
    parser.add_argument("--guard-temp", type=float, default=65.0, help="Temperature safety guard used for pass/fail summary.")
    args = parser.parse_args()

    paths = args.logs
    if not paths:
        paths = sorted(Path("logs").glob("policy_trace_replay_*.csv"), key=lambda p: p.stat().st_mtime)[-args.latest :]
    rows = load_rows(paths)
    if not rows:
        raise RuntimeError("No rows found in selected logs.")

    current_columns = [column for column in rows[0][1] if column.startswith("curr_ma_")]
    thresholds = sorted({1000.0, 1500.0, 2000.0, 2500.0, args.guard_current})
    threshold_counts: dict[float, dict[str, int]] = {threshold: {} for threshold in thresholds}
    spikes: list[tuple[float, Path, str, str, float, float, float, float]] = []
    by_servo: dict[str, list[tuple[float, float, float]]] = {}
    max_current_seen = 0.0
    max_temp_seen = float("-inf")

    for path, row in rows:
        for column in current_columns:
            idx, name = servo_name_from_current_col(column)
            try:
                current = abs(float(row[column]))
                target = float(row[f"target_{idx}_{name}"])
                position = float(row[f"pos_{idx}_{name}"])
                max_temp = float(row["max_temp_c"])
            except (KeyError, TypeError, ValueError):
                continue

            max_current_seen = max(max_current_seen, current)
            max_temp_seen = max(max_temp_seen, max_temp)
            by_servo.setdefault(name, []).append((target, current, position))
            for threshold in thresholds:
                if current >= threshold:
                    threshold_counts[threshold][name] = threshold_counts[threshold].get(name, 0) + 1
            if current >= args.spike_threshold:
                spikes.append((current, path, row.get("label", ""), name, target, position, target - position, max_temp))

    print(f"Analyzed {len(paths)} log file(s), {len(rows)} sampled row(s).")
    print(
        f"Guard summary: max_current={max_current_seen:.1f}mA "
        f"(limit {args.guard_current:.1f}mA), max_temp={max_temp_seen:.1f}C "
        f"(limit {args.guard_temp:.1f}C)"
    )
    if max_current_seen < args.guard_current and max_temp_seen < args.guard_temp:
        print("Guard result: PASS")
    else:
        print("Guard result: FAIL")
    print("\nHigh-current sample counts:")
    for threshold in thresholds:
        print(f"  >= {threshold:.0f} mA")
        if not threshold_counts[threshold]:
            print("    none")
            continue
        for name, count in sorted(threshold_counts[threshold].items(), key=lambda item: -item[1]):
            print(f"    {name:13s} {count}")

    print(f"\nTop spikes >= {args.spike_threshold:.0f} mA:")
    if not spikes:
        print("  none")
    for current, path, label, name, target, position, error, max_temp in sorted(spikes, reverse=True)[:20]:
        print(
            f"  {current:7.1f} mA {name:13s} {path.name:38s} {label:12s} "
            f"target={target:.3f} pos={position:.3f} err={error:+.3f} maxTemp={max_temp:.1f}C"
        )

    print("\nCurrent by target-position bin:")
    for name, values in sorted(by_servo.items()):
        print(f"  {name}")
        bins: dict[float, list[float]] = {}
        for target, current, _position in values:
            bin_start = math.floor(target / args.bin_width) * args.bin_width
            bins.setdefault(bin_start, []).append(current)
        for bin_start, currents in sorted(bins.items()):
            mean = sum(currents) / len(currents)
            print(
                f"    target {bin_start:.2f}-{bin_start + args.bin_width:.2f}: "
                f"n={len(currents):3d} max={max(currents):7.1f} mean={mean:6.1f}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
