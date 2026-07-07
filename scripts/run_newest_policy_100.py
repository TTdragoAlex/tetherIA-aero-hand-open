#!/usr/bin/env python3
"""Run the newest trained cube-rotation policy at 100% with standard guards.

This is a small wrapper around replay_policy_trace_safe.py so we can repeat the
same sim-to-real test without manually rebuilding a long command each time.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / "logs"
REPLAY = REPO_ROOT / "scripts" / "replay_policy_trace_safe.py"
ANALYZE = REPO_ROOT / "scripts" / "analyze_policy_replay_logs.py"


def latest_replay_log() -> Path | None:
    logs = sorted(LOG_DIR.glob("policy_trace_replay_*.csv"), key=lambda path: path.stat().st_mtime)
    return logs[-1] if logs else None


def build_replay_command(args: argparse.Namespace) -> list[str]:
    sample_every = args.sample_every
    if sample_every is None:
        sample_every = 1 if args.strict_sampling else (5 if args.short else 10)
    action_sign = args.action_sign
    if args.real_thumb_abd:
        action_sign = "thumb_abd=-1,thumb_flex=-1,pinky=-1"

    command = [
        sys.executable,
        str(REPLAY),
        "--mapping-mode",
        "signed",
        "--action-sign",
        action_sign,
        "--playback-scale",
        "1.0",
        "--allow-higher-scale",
        "--interpolate-steps",
        str(args.interpolate_steps),
        "--sample-every",
        str(sample_every),
        "--abort-current",
        str(args.guard_current),
        "--abort-temp",
        str(args.guard_temp),
    ]

    if args.run:
        command.append("--run")
    if args.short:
        command.extend(["--max-steps", str(args.short_steps)])
    cap_specs = []
    if args.target_cap:
        cap_specs.append(args.target_cap)
    if args.middle_cap is not None:
        cap_specs.append(f"middle={args.middle_cap}")
    if args.real_thumb_abd and not args.no_thumb_abd_cap and "thumb_abd=" not in ",".join(cap_specs):
        cap_specs.append(f"thumb_abd={args.thumb_abd_cap}")
    if cap_specs:
        command.extend(["--target-cap", ",".join(cap_specs)])
    if args.target_bias:
        command.extend(["--target-bias", args.target_bias])
    if args.target_scale:
        command.extend(["--target-scale", args.target_scale])
    if args.max_step_delta:
        command.extend(["--max-step-delta", args.max_step_delta])
    if args.pregrasp:
        command.extend(["--pregrasp", args.pregrasp])
    if args.pregrasp_duration is not None:
        command.extend(["--pregrasp-duration", str(args.pregrasp_duration)])
    if args.pregrasp_hold is not None:
        command.extend(["--pregrasp-hold", str(args.pregrasp_hold)])
    if args.port:
        command.extend(["--port", args.port])

    return command


def run_analysis(log_path: Path, args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(ANALYZE),
        str(log_path),
        "--guard-current",
        str(args.guard_current),
        "--guard-temp",
        str(args.guard_temp),
        "--spike-threshold",
        str(args.spike_threshold),
    ]
    print("\nAnalyzing replay log:")
    print(" ".join(command))
    return subprocess.run(command, cwd=REPO_ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Repeatable newest-policy 100% cube rotation test.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--short", action="store_true", help="Run only the first part of the policy.")
    mode.add_argument("--full", action="store_true", help="Run the full policy.")
    parser.add_argument("--run", action="store_true", help="Actually move the hand. Omit for dry-run summary only.")
    parser.add_argument("--short-steps", type=int, default=80, help="Trace samples used by --short before interpolation.")
    parser.add_argument("--interpolate-steps", type=int, default=5, help="Smooth substeps per policy sample.")
    parser.add_argument("--strict-sampling", action="store_true", help="Log and guard-check every hardware step.")
    parser.add_argument("--sample-every", type=int, help="Override telemetry sampling interval.")
    parser.add_argument("--guard-current", type=float, default=4000.0, help="Abort current in mA.")
    parser.add_argument("--guard-temp", type=float, default=60.0, help="Abort temperature in C.")
    parser.add_argument("--spike-threshold", type=float, default=1500.0, help="Analysis spike threshold in mA.")
    parser.add_argument(
        "--action-sign",
        default="thumb_flex=-1,pinky=-1",
        help=(
            "Signed mapping override. Default is 'thumb_flex=-1,pinky=-1'. "
            "Use this to test sign flips, e.g. 'thumb_abd=-1,thumb_flex=-1,pinky=-1'."
        ),
    )
    parser.add_argument(
        "--real-thumb-abd",
        action="store_true",
        help=(
            "Use the real-hand thumb-abduction sign convention: sim negative thumb CMC "
            "abduction maps to increasing physical thumb_abd."
        ),
    )
    parser.add_argument(
        "--thumb-abd-cap",
        type=float,
        default=0.35,
        help="Safety cap automatically added with --real-thumb-abd unless target-cap already includes thumb_abd.",
    )
    parser.add_argument(
        "--no-thumb-abd-cap",
        action="store_true",
        help="Do not add the automatic thumb_abd safety cap when --real-thumb-abd is used.",
    )
    parser.add_argument(
        "--middle-cap",
        type=float,
        help="Diagnostic only: cap middle target while keeping 100% policy scale on other channels.",
    )
    parser.add_argument(
        "--target-cap",
        help=(
            "Diagnostic only: arbitrary cap spec forwarded to replay, e.g. "
            "'middle=0.50,index=0.58'. Keeps playback-scale at 100%."
        ),
    )
    parser.add_argument(
        "--target-bias",
        help=(
            "Diagnostic only: add per-channel target offsets before caps, e.g. "
            "'thumb_abd=-0.08,thumb_flex=0.04'."
        ),
    )
    parser.add_argument(
        "--target-scale",
        help=(
            "Diagnostic only: scale per-channel motion around raw rest before bias/caps, e.g. "
            "'index=0.75,middle=0.75,pinky=0.8'."
        ),
    )
    parser.add_argument("--max-step-delta", help="Optional replay slew limit, forwarded as name=value spec.")
    parser.add_argument("--pregrasp", help="Optional pre-grasp target spec forwarded to replay.")
    parser.add_argument("--pregrasp-duration", type=float)
    parser.add_argument("--pregrasp-hold", type=float)
    parser.add_argument("--port", help="Optional serial port override.")
    args = parser.parse_args()

    before_log = latest_replay_log()
    replay_command = build_replay_command(args)
    print("Replay command:")
    print(" ".join(replay_command), flush=True)
    replay_result = subprocess.run(replay_command, cwd=REPO_ROOT)

    after_log = latest_replay_log()
    if args.run and after_log and after_log != before_log:
        analysis_result = run_analysis(after_log, args)
    else:
        analysis_result = 0
        if args.run:
            print("\nNo new replay log was found to analyze.")

    return replay_result.returncode or analysis_result


if __name__ == "__main__":
    raise SystemExit(main())
