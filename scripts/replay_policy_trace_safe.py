#!/usr/bin/env python3
"""Dry-run or safely replay an exported sim policy trace on the Aero Hand.

Default mode is analysis-only. Add --run only after the hand is connected,
powered, clear of obstacles, and you are ready to cut power.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, DEFAULT_CALIBRATION_PATH, fmt, load_raw_rest  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402


DEFAULT_TRACE = REPO_ROOT / "sim" / "policy_exports" / "mild_transfer_newest_trace_20260617" / "mild_transfer_trace.csv"
DEFAULT_METADATA = DEFAULT_TRACE.with_name("mild_transfer_trace_metadata.json")
LOG_DIR = REPO_ROOT / "logs"


@dataclass
class TraceSample:
    step: int
    time_s: float
    target: list[float]
    debug: dict[str, object] | None = None


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def channel_index(label: str) -> int:
    normalized = label.strip().lower()
    if normalized.startswith("ch") and normalized[2:].isdigit():
        idx = int(normalized[2:])
    elif normalized.isdigit():
        idx = int(normalized)
    else:
        matches = [idx for idx, name in enumerate(CHANNEL_NAMES) if name.lower() == normalized]
        if not matches:
            raise ValueError(f"Unknown channel '{label}'. Valid names: {', '.join(CHANNEL_NAMES)}")
        idx = matches[0]
    if idx < 0 or idx >= len(CHANNEL_NAMES):
        raise ValueError(f"Channel index out of range: {label}")
    return idx


def parse_channel_values(spec: str | None, *, default: float | None = None) -> list[float | None]:
    values: list[float | None] = [default] * len(CHANNEL_NAMES)
    if not spec:
        return values
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Expected name=value in '{item}'")
        name, raw_value = item.split("=", 1)
        value = float(raw_value)
        if name.strip().lower() in ("all", "default", "*"):
            values = [value] * len(CHANNEL_NAMES)
            continue
        values[channel_index(name)] = value
    return values


SIM_HOME_CTRL = [0.09, 0.09, 0.09, 0.09, 0.75, 0.035, 0.1]
SIM_ACTION_SCALE = [0.02, 0.02, 0.02, 0.02, 0.7, 0.003, 0.012]
SIM_POLICY_CTRL_MIN = [0.07, 0.07, 0.07, 0.07, 0.05, 0.032, 0.088]
SIM_POLICY_CTRL_MAX = [0.11, 0.11, 0.11, 0.11, 1.45, 0.038, 0.112]
SIM_XML_CTRL_MIN = [0.05852, 0.05852, 0.05852, 0.05852, -0.1, 0.026152, 0.081568]
SIM_XML_CTRL_MAX = [0.110387, 0.110387, 0.110387, 0.110387, 1.75, 0.038389, 0.112138]

# Physical raw-normalized anchors in CHANNEL_NAMES order:
# thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky.
AFFINE_REAL_EXTEND = [0.15, 0.08, 0.08, 0.10, 0.10, 0.10, 0.10]
AFFINE_REAL_FLEX = [0.70, 0.42, 0.42, 0.55, 0.55, 0.55, 0.60]
AFFINE_TENDON_CHANNELS = {"thumb_flex", "thumb_tendon", "index", "middle", "ring", "pinky"}


def metadata_raw_rest(metadata: dict, calibration: Path) -> list[float]:
    calibration_rest = load_raw_rest(calibration)
    raw_rest = metadata.get("raw_rest")
    if raw_rest is None:
        raw_rest = metadata.get("action_mapping", {}).get("raw_rest")

    if isinstance(raw_rest, dict):
        return [
            float(raw_rest.get(name, calibration_rest[idx]))
            for idx, name in enumerate(CHANNEL_NAMES)
        ]
    if raw_rest is not None:
        return [float(v) for v in raw_rest]
    return calibration_rest


def load_trace(path: Path) -> list[TraceSample]:
    rows: list[TraceSample] = []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            data = data.get("rows") or data.get("samples") or data.get("trace")
        if not isinstance(data, list):
            raise RuntimeError(f"Unsupported JSON trace format: {path}")
        for idx, row in enumerate(data):
            if "physical_target" not in row:
                raise RuntimeError(f"JSON trace row is missing physical_target: {path}")
            step = int(row.get("step", idx))
            time_s = float(row.get("time_s", step * 0.05))
            target = [clamp01(value) for value in row["physical_target"]]
            if len(target) != len(CHANNEL_NAMES):
                raise RuntimeError(
                    f"Expected {len(CHANNEL_NAMES)} physical targets, got {len(target)} in {path}"
                )
            rows.append(TraceSample(step, time_s, target))
        if not rows:
            raise RuntimeError(f"Trace is empty: {path}")
        return rows

    with path.open(newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            target = [
                clamp01(row[f"physical_target_{idx}_{name}"])
                for idx, name in enumerate(CHANNEL_NAMES)
            ]
            time_s = row.get("time_s")
            if time_s is None:
                time_s = row.get("elapsed_s")
            if time_s is None:
                time_s = len(rows) * 0.05
            rows.append(TraceSample(int(row["step"]), float(time_s), target))
    if not rows:
        raise RuntimeError(f"Trace is empty: {path}")
    return rows


def load_sim_action_trace(
    path: Path,
    metadata: dict,
    playback_scale: float,
    calibration: Path,
    mapping_mode: str,
    action_sign_spec: str | None,
    action_center_spec: str | None = None,
) -> list[TraceSample]:
    raw_rest = load_raw_rest(calibration)
    action_mapping = metadata.get("action_mapping", {})
    sim_order = (
        metadata.get("sim_actuator_order")
        or metadata.get("sim_action_order")
        or action_mapping.get("sim_action_order")
        or action_mapping.get("sim_actuator_order")
    )
    sim_to_physical_index = metadata.get("sim_to_physical_index") or action_mapping["sim_to_physical_index"]
    action_signs = parse_channel_values(action_sign_spec, default=1.0)
    action_centers = parse_channel_values(action_center_spec)
    rows: list[TraceSample] = []

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            data = data.get("rows") or data.get("samples") or data.get("trace")
        if not isinstance(data, list):
            raise RuntimeError(f"Unsupported JSON trace format: {path}")
        iterable = data
    else:
        file = path.open(newline="")
        reader = csv.DictReader(file)
        iterable = list(reader)
        file.close()

    for row_idx, row in enumerate(iterable):
        target = []
        for physical_idx in range(len(CHANNEL_NAMES)):
            sim_idx = int(sim_to_physical_index[physical_idx])
            if isinstance(row, dict) and "sim_action" in row:
                action = float(row["sim_action"][sim_idx])
            else:
                action = float(row[f"sim_action_{sim_idx}_{sim_order[sim_idx]}"])
            signed_action = float(action_signs[physical_idx] or 1.0) * action
            if mapping_mode == "signed":
                mapped_action = signed_action
            elif mapping_mode == "abs":
                mapped_action = abs(signed_action)
            elif mapping_mode == "centered":
                center = action_centers[physical_idx]
                if center is None:
                    center = raw_rest[physical_idx]
                target.append(clamp01(float(center) + playback_scale * signed_action))
                continue
            else:
                raise ValueError(f"Unsupported sim action mapping mode: {mapping_mode}")
            target.append(clamp01(raw_rest[physical_idx] + playback_scale * mapped_action))
        time_s = row.get("time_s") if isinstance(row, dict) else None
        if time_s is None and isinstance(row, dict):
            time_s = row.get("elapsed_s")
        if time_s is None:
            time_s = len(rows) * 0.05
        step = int(row.get("step", row_idx)) if isinstance(row, dict) else row_idx
        rows.append(TraceSample(step, float(time_s), target))

    if not rows:
        raise RuntimeError(f"Trace is empty: {path}")
    return rows


def affine_range_for_mode(mapping_mode: str) -> tuple[list[float], list[float]]:
    if mapping_mode in ("policy_affine", "policy_affine_thumb_flip"):
        return SIM_POLICY_CTRL_MIN, SIM_POLICY_CTRL_MAX
    if mapping_mode in ("xml_affine", "xml_affine_thumb_flip"):
        return SIM_XML_CTRL_MIN, SIM_XML_CTRL_MAX
    raise ValueError(f"Unsupported affine mapping mode: {mapping_mode}")


def load_sim_affine_trace(
    path: Path,
    metadata: dict,
    mapping_mode: str,
    real_extend_spec: str | None = None,
    real_flex_spec: str | None = None,
) -> list[TraceSample]:
    """Map raw sim action through MuJoCo ctrl space into calibrated real targets."""
    action_mapping = metadata.get("action_mapping", {})
    sim_order = (
        metadata.get("sim_actuator_order")
        or metadata.get("sim_action_order")
        or action_mapping.get("sim_action_order")
        or action_mapping.get("sim_actuator_order")
    )
    sim_to_physical_index = metadata.get("sim_to_physical_index") or action_mapping["sim_to_physical_index"]
    sim_ctrl_min, sim_ctrl_max = affine_range_for_mode(mapping_mode)
    real_extend_overrides = parse_channel_values(real_extend_spec)
    real_flex_overrides = parse_channel_values(real_flex_spec)
    real_extend = [
        AFFINE_REAL_EXTEND[idx] if real_extend_overrides[idx] is None else float(real_extend_overrides[idx])
        for idx in range(len(CHANNEL_NAMES))
    ]
    real_flex = [
        AFFINE_REAL_FLEX[idx] if real_flex_overrides[idx] is None else float(real_flex_overrides[idx])
        for idx in range(len(CHANNEL_NAMES))
    ]

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            data = data.get("rows") or data.get("samples") or data.get("trace")
        if not isinstance(data, list):
            raise RuntimeError(f"Unsupported JSON trace format: {path}")
        iterable = data
    else:
        with path.open(newline="") as file:
            iterable = list(csv.DictReader(file))

    rows: list[TraceSample] = []
    for row_idx, row in enumerate(iterable):
        raw_sim_action = [0.0] * len(CHANNEL_NAMES)
        sim_ctrl = [0.0] * len(CHANNEL_NAMES)
        sim_norm = [0.0] * len(CHANNEL_NAMES)
        real_preclip = [0.0] * len(CHANNEL_NAMES)
        target = [0.0] * len(CHANNEL_NAMES)

        for physical_idx, physical_name in enumerate(CHANNEL_NAMES):
            sim_idx = int(sim_to_physical_index[physical_idx])
            if isinstance(row, dict) and "sim_action" in row:
                action = float(row["sim_action"][sim_idx])
            else:
                action = float(row[f"sim_action_{sim_idx}_{sim_order[sim_idx]}"])

            ctrl = SIM_HOME_CTRL[sim_idx] + action * SIM_ACTION_SCALE[sim_idx]
            denom = sim_ctrl_max[sim_idx] - sim_ctrl_min[sim_idx]
            norm = 0.5 if abs(denom) < 1e-12 else (ctrl - sim_ctrl_min[sim_idx]) / denom
            norm = clamp01(norm)

            if physical_name in AFFINE_TENDON_CHANNELS:
                # Sim norm 0 is shortened/flexed; sim norm 1 is lengthened/extended.
                real = real_flex[physical_idx] + norm * (
                    real_extend[physical_idx] - real_flex[physical_idx]
                )
            else:
                if "thumb_flip" in mapping_mode:
                    # Test whether sim +abduction is opposite to the real raw thumb_abd direction.
                    real = real_flex[physical_idx] + norm * (
                        real_extend[physical_idx] - real_flex[physical_idx]
                    )
                else:
                    # Thumb abduction direct low-to-high interpolation.
                    real = real_extend[physical_idx] + norm * (
                        real_flex[physical_idx] - real_extend[physical_idx]
                    )

            raw_sim_action[physical_idx] = action
            sim_ctrl[physical_idx] = ctrl
            sim_norm[physical_idx] = norm
            real_preclip[physical_idx] = real
            target[physical_idx] = clamp01(real)

        time_s = row.get("time_s") if isinstance(row, dict) else None
        if time_s is None and isinstance(row, dict):
            time_s = row.get("elapsed_s")
        if time_s is None:
            time_s = len(rows) * 0.05
        step = int(row.get("step", row_idx)) if isinstance(row, dict) else row_idx
        rows.append(
            TraceSample(
                step,
                float(time_s),
                target,
                debug={
                    "mapping_candidate": mapping_mode,
                    "raw_sim_action_physical_order": raw_sim_action,
                    "sim_ctrl_physical_order": sim_ctrl,
                    "sim_norm_physical_order": sim_norm,
                    "real_target_preclip": real_preclip,
                    "real_target_after_clip": target[:],
                },
            )
        )

    if not rows:
        raise RuntimeError(f"Trace is empty: {path}")
    return rows


def rescale_trace(
    samples: list[TraceSample],
    metadata: dict,
    playback_scale: float,
    calibration: Path,
) -> list[TraceSample]:
    """Recompute physical targets at the requested scale around rest."""
    default_scale = float(metadata.get("default_playback_scale", metadata.get("playback_scale", 0.25)))
    raw_rest = load_raw_rest(calibration)
    exported_rest = metadata_raw_rest(metadata, calibration)
    if abs(playback_scale - default_scale) < 1e-9:
        return samples

    rescaled: list[TraceSample] = []
    for sample in samples:
        target = []
        for idx, value in enumerate(sample.target):
            # The exported trace used rest + default_scale * mapped_action.
            mapped_action = (value - exported_rest[idx]) / default_scale
            target.append(clamp01(raw_rest[idx] + playback_scale * mapped_action))
        rescaled.append(TraceSample(sample.step, sample.time_s, target))
    return rescaled


def apply_target_limits(
    samples: list[TraceSample],
    calibration: Path,
    cap_spec: str | None,
    max_step_delta_spec: str | None,
) -> list[TraceSample]:
    """Apply upper target caps and slew-rate limits without changing the trace file."""
    caps = parse_channel_values(cap_spec)
    max_step_delta = parse_channel_values(max_step_delta_spec)
    if all(value is None for value in caps) and all(value is None for value in max_step_delta):
        return samples

    previous = load_raw_rest(calibration)
    limited: list[TraceSample] = []
    for sample in samples:
        target = []
        for idx, desired in enumerate(sample.target):
            cap = caps[idx]
            if cap is not None:
                desired = min(desired, cap)

            delta_limit = max_step_delta[idx]
            if delta_limit is not None:
                delta = desired - previous[idx]
                if delta > delta_limit:
                    desired = previous[idx] + delta_limit
                elif delta < -delta_limit:
                    desired = previous[idx] - delta_limit

            target.append(clamp01(desired))
        debug = dict(sample.debug or {})
        if debug:
            debug["real_target_after_clip"] = target[:]
        limited.append(TraceSample(sample.step, sample.time_s, target, debug or sample.debug))
        previous = target

    return limited


def apply_target_bias(samples: list[TraceSample], bias_spec: str | None) -> list[TraceSample]:
    """Add per-channel offsets to physical targets without changing the trace file."""
    biases = parse_channel_values(bias_spec, default=0.0)
    if not bias_spec or all(abs(float(value or 0.0)) < 1e-12 for value in biases):
        return samples

    biased: list[TraceSample] = []
    for sample in samples:
        target = [
            clamp01(sample.target[idx] + float(biases[idx] or 0.0))
            for idx in range(len(CHANNEL_NAMES))
        ]
        biased.append(TraceSample(sample.step, sample.time_s, target, sample.debug))
    return biased


def apply_target_scale(
    samples: list[TraceSample],
    calibration: Path,
    scale_spec: str | None,
) -> list[TraceSample]:
    """Scale per-channel motion around raw rest without changing the trace file."""
    scales = parse_channel_values(scale_spec, default=1.0)
    if not scale_spec or all(abs(float(value or 1.0) - 1.0) < 1e-12 for value in scales):
        return samples

    rest = load_raw_rest(calibration)
    scaled: list[TraceSample] = []
    for sample in samples:
        target = [
            clamp01(rest[idx] + float(scales[idx] or 1.0) * (sample.target[idx] - rest[idx]))
            for idx in range(len(CHANNEL_NAMES))
        ]
        scaled.append(TraceSample(sample.step, sample.time_s, target, sample.debug))
    return scaled


def interpolate_samples(
    samples: list[TraceSample],
    calibration: Path,
    substeps: int,
    dt_s: float,
) -> list[TraceSample]:
    if substeps <= 1:
        return samples

    previous = load_raw_rest(calibration)
    interpolated: list[TraceSample] = []
    out_idx = 0
    for sample in samples:
        for substep in range(1, substeps + 1):
            alpha = substep / substeps
            target = [
                clamp01(previous[idx] + alpha * (sample.target[idx] - previous[idx]))
                for idx in range(len(CHANNEL_NAMES))
            ]
            interpolated.append(TraceSample(sample.step, out_idx * dt_s, target, sample.debug))
            out_idx += 1
        previous = sample.target
    return interpolated


def make_pregrasp_samples(
    calibration: Path,
    target_spec: str | None,
    duration_s: float,
    rate: float,
    max_step_delta_spec: str | None,
) -> list[TraceSample]:
    if not target_spec or duration_s <= 0.0:
        return []

    rest = load_raw_rest(calibration)
    requested = parse_channel_values(target_spec)
    final_target = [
        clamp01(requested[idx] if requested[idx] is not None else rest[idx])
        for idx in range(len(CHANNEL_NAMES))
    ]

    steps = max(1, int(round(duration_s * rate)))
    samples: list[TraceSample] = []
    for step in range(steps):
        alpha = (step + 1) / steps
        target = [
            clamp01(rest[idx] + alpha * (final_target[idx] - rest[idx]))
            for idx in range(len(CHANNEL_NAMES))
        ]
        samples.append(TraceSample(-(steps - step), alpha * duration_s - duration_s, target))

    return apply_target_limits(samples, calibration, None, max_step_delta_spec)


def summarize(samples: list[TraceSample]) -> None:
    mins = [min(sample.target[i] for sample in samples) for i in range(7)]
    maxs = [max(sample.target[i] for sample in samples) for i in range(7)]
    spans = [maxs[i] - mins[i] for i in range(7)]
    max_delta = [0.0] * 7
    for prev, cur in zip(samples, samples[1:]):
        for i in range(7):
            max_delta[i] = max(max_delta[i], abs(cur.target[i] - prev.target[i]))

    print("Trace summary:")
    print(f"  samples: {len(samples)}")
    print(f"  duration_s: {samples[-1].time_s:.2f}")
    for idx, name in enumerate(CHANNEL_NAMES):
        status = "moves" if spans[idx] >= 0.01 else "mostly_rest"
        print(
            f"  ch{idx}:{name:13s} min={mins[idx]:.4f} max={maxs[idx]:.4f} "
            f"span={spans[idx]:.4f} max_step_delta={max_delta[idx]:.4f} {status}"
        )


def write_log_row(
    writer: csv.DictWriter,
    label: str,
    elapsed_s: float,
    target: list[float],
    pos: list[float],
    curr: list[float],
    temp: list[float],
    debug: dict[str, object] | None = None,
) -> None:
    row: dict[str, float | str] = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "elapsed_s": elapsed_s,
        "label": label,
        "max_abs_current_ma": max(abs(v) for v in curr),
        "max_temp_c": max(temp),
    }
    for idx, name in enumerate(CHANNEL_NAMES):
        row[f"target_{idx}_{name}"] = target[idx]
        row[f"pos_{idx}_{name}"] = pos[idx]
        row[f"curr_ma_{idx}_{name}"] = curr[idx]
        row[f"temp_c_{idx}_{name}"] = temp[idx]
    if debug:
        row["mapping_candidate"] = str(debug.get("mapping_candidate", ""))
        for debug_key, prefix in (
            ("raw_sim_action_physical_order", "raw_sim_action"),
            ("sim_ctrl_physical_order", "sim_ctrl"),
            ("sim_norm_physical_order", "sim_norm"),
            ("real_target_preclip", "real_target_preclip"),
            ("real_target_after_clip", "real_target_after_clip"),
        ):
            values = debug.get(debug_key)
            if isinstance(values, list):
                for idx, name in enumerate(CHANNEL_NAMES):
                    if idx < len(values):
                        row[f"{prefix}_{idx}_{name}"] = values[idx]
    writer.writerow(row)


def log_fieldnames() -> list[str]:
    fields = ["timestamp", "elapsed_s", "label", "max_abs_current_ma", "max_temp_c", "mapping_candidate"]
    for idx, name in enumerate(CHANNEL_NAMES):
        fields.extend([
            f"target_{idx}_{name}",
            f"pos_{idx}_{name}",
            f"curr_ma_{idx}_{name}",
            f"temp_c_{idx}_{name}",
            f"raw_sim_action_{idx}_{name}",
            f"sim_ctrl_{idx}_{name}",
            f"sim_norm_{idx}_{name}",
            f"real_target_preclip_{idx}_{name}",
            f"real_target_after_clip_{idx}_{name}",
        ])
    return fields


def run_and_log_sample(
    hand: AeroHandController,
    writer: csv.DictWriter,
    file,
    sample: TraceSample,
    label: str,
    started: float,
    dt: float,
    args: argparse.Namespace,
) -> None:
    hand.send_raw_actuators(sample.target)
    time.sleep(dt)
    curr = hand.get_currents_ma()
    temp = hand.get_temperatures_c()
    pos = hand.get_pos_norm()
    write_log_row(writer, label, time.monotonic() - started, sample.target, pos, curr, temp, sample.debug)
    file.flush()
    max_curr = max(abs(v) for v in curr)
    print(
        f"[{label}] max_curr={max_curr:.1f}mA "
        f"max_temp={max(temp):.1f}C target={fmt(sample.target)}"
    )
    enforce_safety(curr, temp, args.abort_current, args.abort_temp)


def enforce_safety(curr: list[float], temp: list[float], abort_current: float, abort_temp: float) -> None:
    over_curr = [i for i, value in enumerate(curr) if abs(value) >= abort_current]
    over_temp = [i for i, value in enumerate(temp) if value >= abort_temp]
    if not over_curr and not over_temp:
        return
    parts = []
    if over_curr:
        parts.append("current " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={curr[i]:.1f}mA" for i in over_curr))
    if over_temp:
        parts.append("temp " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={temp[i]:.1f}C" for i in over_temp))
    raise RuntimeError("Safety abort: " + "; ".join(parts))


def run_replay(args: argparse.Namespace) -> int:
    metadata = json.loads(args.metadata.read_text())
    if args.mapping_mode == "positive":
        samples = load_trace(args.trace)
        samples = rescale_trace(samples, metadata, args.playback_scale, args.calibration)
    elif args.mapping_mode in (
        "policy_affine",
        "xml_affine",
        "policy_affine_thumb_flip",
        "xml_affine_thumb_flip",
    ):
        samples = load_sim_affine_trace(
            args.trace,
            metadata,
            args.mapping_mode,
            args.affine_real_extend,
            args.affine_real_flex,
        )
    else:
        samples = load_sim_action_trace(
            args.trace,
            metadata,
            args.playback_scale,
            args.calibration,
            args.mapping_mode,
            args.action_sign,
            args.action_center,
        )
    if args.max_steps is not None:
        samples = samples[: args.max_steps]
    samples = apply_target_scale(samples, args.calibration, args.target_scale)
    samples = apply_target_bias(samples, args.target_bias)
    samples = apply_target_limits(samples, args.calibration, args.target_cap, args.max_step_delta)
    samples = interpolate_samples(samples, args.calibration, args.interpolate_steps, 1.0 / args.rate)
    pregrasp_samples = make_pregrasp_samples(
        args.calibration,
        args.pregrasp,
        args.pregrasp_duration,
        args.rate,
        args.pregrasp_max_step_delta or args.max_step_delta,
    )

    action_mapping = metadata.get("action_mapping", {})
    print(f"policy: {metadata.get('selected_policy') or metadata.get('env_name', 'unknown')}")
    print(f"checkpoint: {metadata.get('checkpoint') or metadata.get('checkpoint_root', 'unknown')}")
    print(f"mapping: {metadata.get('physical_mapping_mode') or action_mapping.get('formula', 'unknown')}")
    print(f"mapping_mode: {args.mapping_mode}")
    if args.action_sign:
        print(f"action_sign: {args.action_sign}")
    if args.action_center:
        print(f"action_center: {args.action_center}")
    print(f"playback_scale: {args.playback_scale:.3f}")
    if args.target_cap:
        print(f"target_cap: {args.target_cap}")
    if args.target_bias:
        print(f"target_bias: {args.target_bias}")
    if args.target_scale:
        print(f"target_scale: {args.target_scale}")
    if args.affine_real_extend:
        print(f"affine_real_extend: {args.affine_real_extend}")
    if args.affine_real_flex:
        print(f"affine_real_flex: {args.affine_real_flex}")
    if args.max_step_delta:
        print(f"max_step_delta: {args.max_step_delta}")
    if args.interpolate_steps > 1:
        print(f"interpolate_steps: {args.interpolate_steps}")
    if args.pregrasp:
        print(f"pregrasp: {args.pregrasp}")
        print(f"pregrasp_duration: {args.pregrasp_duration:.2f}s")
        if args.pregrasp_max_step_delta:
            print(f"pregrasp_max_step_delta: {args.pregrasp_max_step_delta}")
        print("Pre-grasp summary:")
        summarize(pregrasp_samples)
    summarize(samples)

    if args.dry_run_map:
        print("\nDry-run mapped targets. No serial connection or movement happened.")
        for idx, sample in enumerate(samples[: args.max_steps or len(samples)]):
            debug = sample.debug or {}
            print(f"[{idx:04d}] step={sample.step} target={fmt(sample.target)}")
            for key in (
                "raw_sim_action_physical_order",
                "sim_ctrl_physical_order",
                "sim_norm_physical_order",
                "real_target_preclip",
                "real_target_after_clip",
            ):
                values = debug.get(key)
                if isinstance(values, list):
                    print(f"       {key}: {fmt([float(v) for v in values])}")
        return 0

    if args.playback_scale > 0.25 and not args.allow_higher_scale:
        raise RuntimeError("Refusing playback_scale > 0.25 without --allow-higher-scale")

    if not args.run:
        print("\nDry run only. No serial connection or movement happened.")
        print("When ready later, connect the hand and add --run.")
        return 0

    log_path = args.log or LOG_DIR / f"policy_trace_replay_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    dt = 1.0 / args.rate

    with log_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=log_fieldnames())
        writer.writeheader()
        with AeroHandController(args.port, args.baud) as hand:
            try:
                rest = hand.apply_rest(args.calibration, settle_s=args.rest_settle)
                curr = hand.get_currents_ma()
                temp = hand.get_temperatures_c()
                pos = hand.get_pos_norm()
                write_log_row(writer, "initial_rest", time.monotonic() - started, rest, pos, curr, temp)
                enforce_safety(curr, temp, args.abort_current, args.abort_temp)

                for idx, sample in enumerate(pregrasp_samples):
                    if idx % args.sample_every == 0 or idx == len(pregrasp_samples) - 1:
                        run_and_log_sample(
                            hand,
                            writer,
                            file,
                            sample,
                            f"pregrasp_{idx}",
                            started,
                            dt,
                            args,
                        )
                    else:
                        hand.send_raw_actuators(sample.target)
                        time.sleep(dt)

                if pregrasp_samples and args.pregrasp_hold > 0.0:
                    time.sleep(args.pregrasp_hold)
                    curr = hand.get_currents_ma()
                    temp = hand.get_temperatures_c()
                    pos = hand.get_pos_norm()
                    write_log_row(
                        writer,
                        "pregrasp_hold",
                        time.monotonic() - started,
                        pregrasp_samples[-1].target,
                        pos,
                        curr,
                        temp,
                        pregrasp_samples[-1].debug,
                    )
                    file.flush()
                    enforce_safety(curr, temp, args.abort_current, args.abort_temp)

                for idx, sample in enumerate(samples):
                    hand.send_raw_actuators(sample.target)
                    time.sleep(dt)
                    if idx % args.sample_every == 0 or idx == len(samples) - 1:
                        curr = hand.get_currents_ma()
                        temp = hand.get_temperatures_c()
                        pos = hand.get_pos_norm()
                        write_log_row(
                            writer,
                            f"step_{sample.step}",
                            time.monotonic() - started,
                            sample.target,
                            pos,
                            curr,
                            temp,
                            sample.debug,
                        )
                        file.flush()
                        max_curr = max(abs(v) for v in curr)
                        print(
                            f"[{idx:04d}] max_curr={max_curr:.1f}mA "
                            f"max_temp={max(temp):.1f}C target={fmt(sample.target)}"
                        )
                        enforce_safety(curr, temp, args.abort_current, args.abort_temp)
            except Exception:
                print("\n[recovery] sending raw rest after exception/abort")
                hand.apply_rest(args.calibration, settle_s=args.rest_settle)
                raise

    print(f"\nReplay complete. Log: {log_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or safely replay an exported mild_transfer policy trace.")
    parser.add_argument("--run", action="store_true", help="Actually move the physical hand. Omit for dry run.")
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION_PATH)
    parser.add_argument("--playback-scale", type=float, default=0.25, help="Conservative scale applied to positive sim actions.")
    parser.add_argument("--allow-higher-scale", action="store_true", help="Permit playback scale above 0.25.")
    parser.add_argument(
        "--mapping-mode",
        choices=(
            "positive",
            "signed",
            "abs",
            "centered",
            "policy_affine",
            "xml_affine",
            "policy_affine_thumb_flip",
            "xml_affine_thumb_flip",
        ),
        default="positive",
        help=(
            "Target mapping. positive keeps the exported raw_rest + scale * max(0, action). "
            "signed uses raw_rest + scale * signed action. abs uses raw_rest + scale * abs(action). "
            "centered uses action_center + scale * signed action. "
            "policy_affine/xml_affine convert raw sim action to MuJoCo ctrl, normalize, then map to real calibrated anchors."
        ),
    )
    parser.add_argument(
        "--dry-run-map",
        action="store_true",
        help="Print mapped sim action/ctrl/norm/real targets and exit without moving hardware, even if --run is present.",
    )
    parser.add_argument(
        "--action-center",
        help=(
            "Comma-separated physical centers for --mapping-mode centered, e.g. "
            "'thumb_abd=0.45,index=0.35,middle=0.35,ring=0.35,pinky=0.35'. "
            "Channels omitted default to raw rest."
        ),
    )
    parser.add_argument(
        "--action-sign",
        help=(
            "Comma-separated signs for sim-action mapping, e.g. "
            "'thumb_flex=-1,pinky=-1,ring=-1,thumb_abd=-1'. "
            "Only used with --mapping-mode signed or abs."
        ),
    )
    parser.add_argument(
        "--target-cap",
        help=(
            "Comma-separated upper caps, e.g. "
            "'index=0.30,thumb_tendon=0.18,middle=0.40'. "
            "Use all=VALUE to cap every channel."
        ),
    )
    parser.add_argument(
        "--target-bias",
        help=(
            "Comma-separated per-channel offsets applied before caps/slew limits, e.g. "
            "'thumb_abd=-0.08,thumb_flex=0.04'."
        ),
    )
    parser.add_argument(
        "--target-scale",
        help=(
            "Comma-separated per-channel motion scales around raw rest before bias/caps, e.g. "
            "'index=0.75,middle=0.75,pinky=0.8'."
        ),
    )
    parser.add_argument(
        "--affine-real-extend",
        help=(
            "Override real actuator extend/open anchors for affine mapping, e.g. "
            "'thumb_abd=0.05,index=0.10'. Channels omitted keep defaults."
        ),
    )
    parser.add_argument(
        "--affine-real-flex",
        help=(
            "Override real actuator flex/closed anchors for affine mapping, e.g. "
            "'thumb_abd=0.95,index=0.55'. Channels omitted keep defaults."
        ),
    )
    parser.add_argument(
        "--max-step-delta",
        help=(
            "Comma-separated per-command slew limits in normalized units, e.g. "
            "'all=0.04,index=0.03,thumb_tendon=0.03'."
        ),
    )
    parser.add_argument("--max-steps", type=int, help="Limit replay to the first N trace samples.")
    parser.add_argument("--rate", type=float, default=20.0, help="Hardware command rate in Hz.")
    parser.add_argument(
        "--interpolate-steps",
        type=int,
        default=1,
        help="Insert this many smooth substeps per policy sample while preserving each final policy target.",
    )
    parser.add_argument("--sample-every", type=int, default=5, help="Telemetry interval in command steps.")
    parser.add_argument("--rest-settle", type=float, default=0.5)
    parser.add_argument(
        "--pregrasp",
        help=(
            "Optional comma-separated pre-grasp target before replay, e.g. "
            "'thumb_flex=0.06,index=0.10,middle=0.14,ring=0.08,pinky=0.10'."
        ),
    )
    parser.add_argument("--pregrasp-duration", type=float, default=1.0, help="Seconds to ramp from rest to pre-grasp.")
    parser.add_argument("--pregrasp-hold", type=float, default=0.25, help="Seconds to hold pre-grasp before policy replay.")
    parser.add_argument(
        "--pregrasp-max-step-delta",
        help="Optional slew limit just for pre-grasp; defaults to --max-step-delta.",
    )
    parser.add_argument("--warn-current", type=float, default=800.0)
    parser.add_argument("--abort-current", type=float, default=4000.0)
    parser.add_argument("--abort-temp", type=float, default=65.0)
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--log", type=Path)
    args = parser.parse_args()
    return run_replay(args)


if __name__ == "__main__":
    raise SystemExit(main())
