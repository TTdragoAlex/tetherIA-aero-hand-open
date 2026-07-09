#!/usr/bin/env python3
"""Run named sim-to-real mapping candidates for short real-hand comparison.

The point of this script is not to tune gains forever. It runs broad mapping
hypotheses against the same known-good sim rollout so the user can rate each
candidate as bad/closer/best.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TRACE = (
    REPO_ROOT
    / "sim"
    / "policy_exports"
    / "real_obs_participation_000200540160_corrected_signs_v2"
    / "000200540160_video_rollout0_corrected_signs_v2_trace.json"
)
DEFAULT_METADATA = DEFAULT_TRACE.with_name("000200540160_video_rollout0_corrected_signs_v2_metadata.json")

V2_SIGNS = "thumb_abd=1,thumb_flex=-1,thumb_tendon=1,index=-1,middle=1,ring=-1,pinky=-1"
ALL_POSITIVE = "thumb_abd=1,thumb_flex=1,thumb_tendon=1,index=1,middle=1,ring=1,pinky=1"
FINGERS_POS_THUMB_V2 = "thumb_abd=1,thumb_flex=-1,thumb_tendon=1,index=1,middle=1,ring=1,pinky=1"
FINGERS_INVERTED_THUMB_POS = "thumb_abd=1,thumb_flex=1,thumb_tendon=1,index=-1,middle=-1,ring=-1,pinky=-1"
CENTERS = "thumb_abd=0.45,thumb_flex=0.25,thumb_tendon=0.25,index=0.35,middle=0.35,ring=0.35,pinky=0.35"


@dataclass(frozen=True)
class Candidate:
    name: str
    description: str
    mapping_mode: str
    playback_scale: float
    action_sign: str | None = None
    action_center: str | None = None
    target_cap: str | None = None
    target_bias: str | None = None
    target_scale: str | None = None
    affine_real_extend: str | None = None
    affine_real_flex: str | None = None


CANDIDATES: dict[str, Candidate] = {
    "c01_v2_signed": Candidate(
        name="c01_v2_signed",
        description="Current corrected-sign mapping from sim diagnostic metadata.",
        mapping_mode="signed",
        playback_scale=0.55,
        action_sign=V2_SIGNS,
    ),
    "c02_all_positive": Candidate(
        name="c02_all_positive",
        description="Every positive sim action increases the corresponding real raw actuator.",
        mapping_mode="signed",
        playback_scale=0.55,
        action_sign=ALL_POSITIVE,
    ),
    "c03_fingers_pos_thumb_v2": Candidate(
        name="c03_fingers_pos_thumb_v2",
        description="Finger actions positive-to-close, thumb signs kept from v2.",
        mapping_mode="signed",
        playback_scale=0.55,
        action_sign=FINGERS_POS_THUMB_V2,
    ),
    "c04_centered_v2": Candidate(
        name="c04_centered_v2",
        description="Same v2 signs, but sim actions move around a mid hand pose instead of raw rest.",
        mapping_mode="centered",
        playback_scale=0.30,
        action_sign=V2_SIGNS,
        action_center=CENTERS,
    ),
    "c05_centered_all_positive": Candidate(
        name="c05_centered_all_positive",
        description="All-positive signs around a mid hand pose.",
        mapping_mode="centered",
        playback_scale=0.30,
        action_sign=ALL_POSITIVE,
        action_center=CENTERS,
    ),
    "c06_abs_contact": Candidate(
        name="c06_abs_contact",
        description="Contact-only abs(action) mapping; tests whether sign dynamics are the main issue.",
        mapping_mode="abs",
        playback_scale=0.45,
        action_sign=ALL_POSITIVE,
        target_cap="thumb_abd=0.80,thumb_flex=0.55,thumb_tendon=0.55,index=0.65,middle=0.65,ring=0.65,pinky=0.75",
    ),
    "c07_policy_envelope_affine": Candidate(
        name="c07_policy_envelope_affine",
        description=(
            "Principled mapper: sim action -> MuJoCo ctrl -> policy-envelope sim norm "
            "-> calibrated real actuator anchors."
        ),
        mapping_mode="policy_affine",
        playback_scale=1.0,
        target_cap="thumb_abd=0.80,thumb_flex=0.55,thumb_tendon=0.55,index=0.65,middle=0.65,ring=0.65,pinky=0.70",
    ),
    "c08_xml_ctrlrange_affine": Candidate(
        name="c08_xml_ctrlrange_affine",
        description=(
            "Same calibrated affine mapper as c07, but normalizes MuJoCo ctrl over full XML ctrlrange."
        ),
        mapping_mode="xml_affine",
        playback_scale=1.0,
        target_cap="thumb_abd=0.80,thumb_flex=0.55,thumb_tendon=0.55,index=0.65,middle=0.65,ring=0.65,pinky=0.70",
    ),
    "c09_policy_affine_thumb_flip": Candidate(
        name="c09_policy_affine_thumb_flip",
        description=(
            "Same as c07, but flips only thumb_abd interpolation to test sim/real abduction direction."
        ),
        mapping_mode="policy_affine_thumb_flip",
        playback_scale=1.0,
        target_cap="thumb_abd=0.80,thumb_flex=0.55,thumb_tendon=0.55,index=0.65,middle=0.65,ring=0.65,pinky=0.70",
    ),
    "c10_xml_affine_thumb_flip": Candidate(
        name="c10_xml_affine_thumb_flip",
        description=(
            "Same as c08, but flips only thumb_abd interpolation to test sim/real abduction direction."
        ),
        mapping_mode="xml_affine_thumb_flip",
        playback_scale=1.0,
        target_cap="thumb_abd=0.80,thumb_flex=0.55,thumb_tendon=0.55,index=0.65,middle=0.65,ring=0.65,pinky=0.70",
    ),
    "c11_policy_affine_wide_thumb": Candidate(
        name="c11_policy_affine_wide_thumb",
        description=(
            "Same as c07, but widens the calibrated real thumb_abd endpoint range instead of adding bias."
        ),
        mapping_mode="policy_affine",
        playback_scale=1.0,
        affine_real_extend="thumb_abd=0.05",
        affine_real_flex="thumb_abd=0.95",
        target_cap="thumb_abd=0.95,thumb_flex=0.55,thumb_tendon=0.55,index=0.65,middle=0.65,ring=0.65,pinky=0.70",
    ),
    "c12_policy_affine_wide_thumb_tight_tendons": Candidate(
        name="c12_policy_affine_wide_thumb_tight_tendons",
        description=(
            "Same as c11, plus tighter calibrated thumb tendon endpoints so thumb can curl/contact more."
        ),
        mapping_mode="policy_affine",
        playback_scale=1.0,
        affine_real_extend="thumb_abd=0.05,thumb_flex=0.10,thumb_tendon=0.10",
        affine_real_flex="thumb_abd=0.95,thumb_flex=0.62,thumb_tendon=0.62",
        target_cap="thumb_abd=0.95,thumb_flex=0.70,thumb_tendon=0.70,index=0.65,middle=0.65,ring=0.65,pinky=0.70",
    ),
    "c13_policy_affine_wider_finger_swing_thumb_tendon": Candidate(
        name="c13_policy_affine_wider_finger_swing_thumb_tendon",
        description=(
            "Builds on c12: larger back/forth finger swing, less thumb_flex motion, more thumb_tendon motion."
        ),
        mapping_mode="policy_affine",
        playback_scale=1.0,
        affine_real_extend=(
            "thumb_abd=0.05,thumb_flex=0.22,thumb_tendon=0.00,"
            "index=0.00,middle=0.00,ring=0.00,pinky=0.00"
        ),
        affine_real_flex=(
            "thumb_abd=0.95,thumb_flex=0.50,thumb_tendon=0.72,"
            "index=0.65,middle=0.65,ring=0.65,pinky=0.70"
        ),
        target_cap="thumb_abd=0.95,thumb_flex=0.58,thumb_tendon=0.78,index=0.72,middle=0.72,ring=0.72,pinky=0.76",
    ),
    "c14_policy_affine_full_thumb_abd_swing": Candidate(
        name="c14_policy_affine_full_thumb_abd_swing",
        description=(
            "Builds on c13, but maps thumb_abd across the full 0..1 real range for maximum abduction swing."
        ),
        mapping_mode="policy_affine",
        playback_scale=1.0,
        affine_real_extend=(
            "thumb_abd=0.00,thumb_flex=0.22,thumb_tendon=0.00,"
            "index=0.00,middle=0.00,ring=0.00,pinky=0.00"
        ),
        affine_real_flex=(
            "thumb_abd=1.00,thumb_flex=0.50,thumb_tendon=0.72,"
            "index=0.65,middle=0.65,ring=0.65,pinky=0.70"
        ),
        target_cap="thumb_abd=1.00,thumb_flex=0.58,thumb_tendon=0.78,index=0.72,middle=0.72,ring=0.72,pinky=0.76",
    ),
    "c15_policy_affine_less_clamp_thumb_wrap": Candidate(
        name="c15_policy_affine_less_clamp_thumb_wrap",
        description=(
            "Backs off finger clamp/current while preserving full thumb_abd swing and favoring thumb_tendon over thumb_flex."
        ),
        mapping_mode="policy_affine",
        playback_scale=1.0,
        affine_real_extend=(
            "thumb_abd=0.00,thumb_flex=0.24,thumb_tendon=0.00,"
            "index=0.05,middle=0.05,ring=0.05,pinky=0.05"
        ),
        affine_real_flex=(
            "thumb_abd=1.00,thumb_flex=0.44,thumb_tendon=0.78,"
            "index=0.52,middle=0.52,ring=0.52,pinky=0.56"
        ),
        target_cap="thumb_abd=1.00,thumb_flex=0.52,thumb_tendon=0.84,index=0.58,middle=0.58,ring=0.58,pinky=0.62",
    ),
}


def candidate_command(args: argparse.Namespace, candidate: Candidate) -> list[str]:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "replay_policy_trace_safe.py"),
        "--trace",
        str(args.trace),
        "--metadata",
        str(args.metadata),
        "--mapping-mode",
        candidate.mapping_mode,
        "--playback-scale",
        str(args.playback_scale if args.playback_scale is not None else candidate.playback_scale),
        "--allow-higher-scale",
        "--max-steps",
        str(args.max_steps),
        "--rate",
        str(args.rate),
        "--sample-every",
        str(args.sample_every),
        "--max-step-delta",
        args.max_step_delta,
        "--abort-current",
        str(args.abort_current),
        "--abort-temp",
        str(args.abort_temp),
        "--log",
        str(REPO_ROOT / "logs" / f"mapping_tournament_{candidate.name}.csv"),
    ]
    if candidate.action_sign:
        cmd.extend(["--action-sign", candidate.action_sign])
    if args.run:
        cmd.append("--run")
    if args.dry_run_map:
        cmd.append("--dry-run-map")
    if candidate.action_center:
        cmd.extend(["--action-center", candidate.action_center])
    if candidate.target_cap:
        cmd.extend(["--target-cap", candidate.target_cap])
    if candidate.target_bias:
        cmd.extend(["--target-bias", candidate.target_bias])
    if candidate.target_scale:
        cmd.extend(["--target-scale", candidate.target_scale])
    if candidate.affine_real_extend:
        cmd.extend(["--affine-real-extend", candidate.affine_real_extend])
    if candidate.affine_real_flex:
        cmd.extend(["--affine-real-flex", candidate.affine_real_flex])
    if args.pregrasp:
        cmd.extend(["--pregrasp", args.pregrasp])
        cmd.extend(["--pregrasp-duration", str(args.pregrasp_duration)])
        cmd.extend(["--pregrasp-hold", str(args.pregrasp_hold)])
    return cmd


def print_candidates() -> None:
    for key, candidate in CANDIDATES.items():
        print(f"{key}: {candidate.description}")


def run(args: argparse.Namespace) -> int:
    if args.list:
        print_candidates()
        return 0
    if args.candidate not in CANDIDATES:
        print_candidates()
        raise SystemExit(f"Unknown candidate: {args.candidate}")

    candidate = CANDIDATES[args.candidate]
    cmd = candidate_command(args, candidate)
    print(f"Candidate: {candidate.name}")
    print(candidate.description)
    print("Command:")
    print(" ".join(cmd))
    if args.print_only:
        return 0
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a named sim-to-real mapping candidate.")
    parser.add_argument("--candidate", default="c01_v2_signed")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--run", action="store_true", help="Actually move the hand. Omit for dry-run.")
    parser.add_argument("--print-only", action="store_true")
    parser.add_argument("--dry-run-map", action="store_true", help="Print mapped targets and exit without moving hardware.")
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--max-steps", type=int, default=120)
    parser.add_argument("--rate", type=float, default=12.0)
    parser.add_argument("--sample-every", type=int, default=1)
    parser.add_argument("--playback-scale", type=float)
    parser.add_argument("--max-step-delta", default="all=0.055,thumb_abd=0.07,pinky=0.06")
    parser.add_argument("--abort-current", type=float, default=4000.0)
    parser.add_argument("--abort-temp", type=float, default=65.0)
    parser.add_argument(
        "--pregrasp",
        default="thumb_abd=0.25,thumb_flex=0.08,thumb_tendon=0.08,index=0.12,middle=0.12,ring=0.12,pinky=0.12",
    )
    parser.add_argument("--pregrasp-duration", type=float, default=1.0)
    parser.add_argument("--pregrasp-hold", type=float, default=0.15)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
