#!/usr/bin/env python3
"""Live closed-loop Aero Hand policy controller.

This runs a locally exported Brax PPO actor against live hand telemetry.  It is
not the same as trace replay: every step reads the real hand position/current,
builds the actor observation, infers a new sim action, maps it to physical raw
actuator targets, and sends the target under safety limits.

Default mode is dry-run only. Add --run only when the hand is powered, mounted,
clear/safe, and you are ready to cut power.
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
from typing import Iterable

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from aero_hand_control import AeroHandController, DEFAULT_CALIBRATION_PATH, clamp01, fmt, load_raw_rest  # noqa: E402
from gesture_smoke_test import CHANNEL_NAMES  # noqa: E402

DEFAULT_POLICY = REPO_ROOT / "sim" / "live_actor_export_000200540160" / "actor_policy.npz"
DEFAULT_METADATA = DEFAULT_POLICY.with_name("actor_policy_metadata.json")
DEFAULT_OBSERVATION_CALIBRATION = REPO_ROOT / "sim" / "hand_observation_calibration_20260626.json"
LOG_DIR = REPO_ROOT / "logs"

# Actor action order in the legacy sim policy.
SIM_ACTION_NAMES = ["index", "middle", "ring", "pinky", "thumb_abd", "thumb_flex", "thumb_tendon"]
# Hardware-01 policies output real-order hardware-style commands after u=0.5*(raw+1).
HARDWARE01_ACTION_NAMES = ["thumb_abd", "thumb_flex", "thumb_tendon", "index", "middle", "ring", "pinky"]
# physical channel -> sim action index.
SIM_TO_PHYSICAL_INDEX = [4, 5, 6, 0, 1, 2, 3]
# Corrected v2 signs: physical_target = rest + scale * sign * sim_action[sim_idx]
ACTION_SIGN_BY_PHYSICAL = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0, -1.0]
# Observation blocks: 6 tendon sensors, 1 thumb abduction sensor, 7 force proxies, 7 last sim actions.
TENDON_PHYSICAL_INDEX = [3, 4, 5, 6, 1, 2]  # index, middle, ring, pinky, thumb_flex, thumb_tendon
THUMB_ABD_PHYSICAL_INDEX = 0
# physical current order -> sim actuator force order.
SIM_FORCE_PHYSICAL_INDEX = [3, 4, 5, 6, 0, 1, 2]


@dataclass
class PolicyBundle:
    obs_mean: np.ndarray
    obs_std: np.ndarray
    weights: list[tuple[np.ndarray, np.ndarray]]


@dataclass
class ObservationCalibration:
    """No-object current baseline used to isolate likely contact load."""

    source_path: Path
    position_points: list[np.ndarray]
    current_baseline_ma: list[np.ndarray]
    residual_scale_ma: np.ndarray
    residual_sign: np.ndarray


def silu(x: np.ndarray) -> np.ndarray:
    return np.where(x >= 0.0, x / (1.0 + np.exp(-x)), x * np.exp(x) / (1.0 + np.exp(x)))


def load_policy(path: Path) -> PolicyBundle:
    data = np.load(path)
    weights = []
    for layer in ["hidden_0", "hidden_1", "hidden_2", "hidden_3"]:
        weights.append((data[f"{layer}_kernel"].astype(np.float32), data[f"{layer}_bias"].astype(np.float32)))
    return PolicyBundle(
        obs_mean=data["obs_mean"].astype(np.float32),
        obs_std=np.maximum(data["obs_std"].astype(np.float32), 1e-6),
        weights=weights,
    )


def load_observation_calibration(path: Path) -> ObservationCalibration:
    """Load a per-channel no-object current curve in physical channel order."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Observation calibration not found: {path}. "
            "Create one with scripts/build_observation_calibration.py."
        ) from exc

    if data.get("channel_order") != HARDWARE01_ACTION_NAMES:
        raise ValueError("Observation calibration channel_order must match physical hardware order")
    channels = data.get("channels")
    if not isinstance(channels, list) or len(channels) != 7:
        raise ValueError("Observation calibration must contain seven channel curves")

    position_points: list[np.ndarray] = []
    current_baseline_ma: list[np.ndarray] = []
    residual_scale_ma = []
    residual_sign = []
    for idx, channel in enumerate(channels):
        if channel.get("name") != HARDWARE01_ACTION_NAMES[idx]:
            raise ValueError(f"Observation calibration channel {idx} has an unexpected name")
        positions = np.asarray(channel.get("position", []), dtype=np.float32)
        currents = np.asarray(channel.get("current_baseline_ma", []), dtype=np.float32)
        if len(positions) < 2 or len(positions) != len(currents):
            raise ValueError(f"Observation calibration channel {idx} needs matching position/current curves")
        if np.any(np.diff(positions) <= 0.0):
            raise ValueError(f"Observation calibration channel {idx} positions must be strictly increasing")
        position_points.append(positions)
        current_baseline_ma.append(currents)
        residual_scale_ma.append(float(channel.get("residual_scale_ma", data.get("residual_scale_ma", 400.0))))
        residual_sign.append(float(channel.get("residual_sign", 1.0)))

    if any(value <= 0.0 for value in residual_scale_ma):
        raise ValueError("Observation calibration residual scales must be positive")
    return ObservationCalibration(
        source_path=path,
        position_points=position_points,
        current_baseline_ma=current_baseline_ma,
        residual_scale_ma=np.asarray(residual_scale_ma, dtype=np.float32),
        residual_sign=np.asarray(residual_sign, dtype=np.float32),
    )


def baseline_current_ma(pos_norm: list[float], calibration: ObservationCalibration) -> np.ndarray:
    """Return the signed no-object current expected at each physical servo position."""
    position = np.asarray(pos_norm, dtype=np.float32)
    return np.asarray(
        [
            np.interp(position[idx], calibration.position_points[idx], calibration.current_baseline_ma[idx])
            for idx in range(7)
        ],
        dtype=np.float32,
    )


def calibrated_force_proxy(
    pos_norm: list[float],
    curr_ma: list[float],
    force_reference: np.ndarray,
    calibration: ObservationCalibration,
) -> np.ndarray:
    """Map current above the no-object spring/friction curve into actor force input.

    The simulated actor saw signed actuator-force proxy values.  Real servo
    current includes large pose-dependent spring preload, so preserve the
    actor's trained mean at no contact and add only the calibrated residual.
    """
    current = np.asarray(curr_ma, dtype=np.float32)
    baseline = baseline_current_ma(pos_norm, calibration)
    residual = (current - baseline) / calibration.residual_scale_ma
    proxy = force_reference.astype(np.float32) + calibration.residual_sign * np.tanh(residual)
    return np.clip(proxy, -1.0, 1.0)


def infer_action(policy: PolicyBundle, obs_raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Returns deterministic tanh-normal mode action and raw logits."""
    x = ((obs_raw.astype(np.float32) - policy.obs_mean) / policy.obs_std).astype(np.float32)
    for kernel, bias in policy.weights[:-1]:
        x = silu(x @ kernel + bias)
    logits = x @ policy.weights[-1][0] + policy.weights[-1][1]
    action = np.tanh(logits[:7]).astype(np.float32)
    return action, logits.astype(np.float32)


def physical_from_sim_action(
    sim_action: np.ndarray,
    raw_rest: list[float],
    playback_scale: float,
    action_gain: list[float],
    action_sign: list[float],
) -> list[float]:
    target = []
    for physical_idx in range(7):
        sim_idx = SIM_TO_PHYSICAL_INDEX[physical_idx]
        value = (
            raw_rest[physical_idx]
            + playback_scale
            * action_gain[physical_idx]
            * action_sign[physical_idx]
            * float(sim_action[sim_idx])
        )
        target.append(clamp01(value))
    return target


def hardware01_u_from_raw_action(raw_action: np.ndarray) -> np.ndarray:
    """Convert PPO tanh output [-1, 1] to hardware-style real-order u [0, 1]."""
    return np.clip(0.5 * (raw_action.astype(np.float32) + 1.0), 0.0, 1.0).astype(np.float32)


def physical_from_hardware01_u(
    u_real_order: np.ndarray,
    raw_rest: list[float],
    playback_scale: float,
    action_gain: list[float],
) -> list[float]:
    """Map real-order hardware u targets to physical commands.

    playback_scale ramps from the calibrated rest pose toward the policy
    absolute u target. At 1.0, this sends the policy's hardware-style target
    directly; below 1.0 it is a conservative interpolation from rest.
    """
    target = []
    for physical_idx in range(7):
        desired = float(u_real_order[physical_idx])
        value = raw_rest[physical_idx] + playback_scale * action_gain[physical_idx] * (desired - raw_rest[physical_idx])
        target.append(clamp01(value))
    return target


def apply_slew(target: list[float], previous: list[float], max_step_delta: list[float]) -> list[float]:
    limited = []
    for idx, desired in enumerate(target):
        limit = max_step_delta[idx]
        delta = desired - previous[idx]
        if delta > limit:
            desired = previous[idx] + limit
        elif delta < -limit:
            desired = previous[idx] - limit
        limited.append(clamp01(desired))
    return limited


def apply_target_bias(target: list[float], bias: list[float]) -> list[float]:
    return [clamp01(target[idx] + bias[idx]) for idx in range(7)]


def parse_channel_values(spec: str | None, default: float) -> list[float]:
    values = [default] * 7
    if not spec:
        return values
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        name, raw = item.split("=", 1)
        value = float(raw)
        key = name.strip().lower()
        if key in ("all", "default", "*"):
            values = [value] * 7
            continue
        if key.startswith("ch") and key[2:].isdigit():
            idx = int(key[2:])
        elif key.isdigit():
            idx = int(key)
        else:
            idx = [i for i, n in enumerate(CHANNEL_NAMES) if n.lower() == key][0]
        values[idx] = value
    return values


def parse_channel_overrides(spec: str | None, base_values: Iterable[float]) -> list[float]:
    values = list(base_values)
    if not spec:
        return values
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        name, raw = item.split("=", 1)
        value = float(raw)
        key = name.strip().lower()
        if key in ("all", "default", "*"):
            values = [value] * 7
            continue
        if key.startswith("ch") and key[2:].isdigit():
            idx = int(key[2:])
        elif key.isdigit():
            idx = int(key)
        else:
            idx = [i for i, n in enumerate(CHANNEL_NAMES) if n.lower() == key][0]
        values[idx] = value
    return values


def hardware01_initial_u(policy: PolicyBundle, mode: str, raw_rest: list[float]) -> np.ndarray:
    if mode == "rest":
        return np.asarray(raw_rest, dtype=np.float32)
    if mode == "half":
        return np.full(7, 0.5, dtype=np.float32)
    if mode == "policy_mean":
        return np.clip(policy.obs_mean[:7].astype(np.float32), 0.0, 1.0)
    raise ValueError(f"Unsupported hardware01 initial mode: {mode}")


def ramp_raw_actuators(
    hand: AeroHandController,
    start: list[float],
    end: list[float],
    max_step_delta: list[float],
    rate_hz: float,
    args: argparse.Namespace,
) -> list[float]:
    """Ramp to an initial posture while enforcing the normal hardware aborts."""
    current = list(start)
    while True:
        limited = apply_slew(end, current, max_step_delta)
        hand.send_raw_actuators(limited)
        current = limited
        curr = hand.get_currents_ma()
        temp = hand.get_temperatures_c()
        enforce_safety_with_confirmation(hand, curr, temp, args)
        if all(abs(current[i] - end[i]) < 1e-4 for i in range(7)):
            return current
        time.sleep(1.0 / rate_hz)


def build_obs(
    pos_norm: list[float],
    curr_ma: list[float],
    last_action_obs: np.ndarray,
    raw_rest: list[float],
    position_gain: float,
    thumb_abd_gain: float,
    current_scale_ma: float,
    use_signed_current: bool,
    force_obs_source: str,
    force_obs_reference: np.ndarray,
    observation_calibration: ObservationCalibration | None,
    invert_position_obs: bool,
    obs_mode: str,
    hardware_position_scale: float,
    action_sign: list[float],
) -> np.ndarray:
    obs = np.zeros(21, dtype=np.float32)
    # We feed z-like normalized real deviations through the exported normalizer by
    # creating raw observation values around the trained mean/std in main().
    if obs_mode == "hardware01":
        # Hardware-01 policies were trained on deployable real-order u-like
        # actuator positions: [thumb_abd, thumb_flex, thumb_tendon, index,
        # middle, ring, pinky]. Real GET_POS already arrives in this order.
        obs[:7] = np.clip(np.asarray(pos_norm, dtype=np.float32), 0.0, 1.0)
    elif obs_mode == "hardware":
        # New hardware-observation policies expect the first 7 values in sim
        # action order: index, middle, ring, pinky, thumb_abd, thumb_flex,
        # thumb_tendon.  Invert the physical action mapping:
        #   physical = rest + scale * sign * sim_action
        # so observed real position becomes an estimated sim-action position.
        estimated_sim_position = np.zeros(7, dtype=np.float32)
        scale = max(float(hardware_position_scale), 1e-6)
        for physical_idx in range(7):
            sim_idx = SIM_TO_PHYSICAL_INDEX[physical_idx]
            estimated_sim_position[sim_idx] = (
                action_sign[physical_idx]
                * (float(pos_norm[physical_idx]) - float(raw_rest[physical_idx]))
                / scale
            )
        obs[:7] = np.clip(estimated_sim_position, -3.0, 3.0)
    elif obs_mode == "tendon_guess":
        tendon_values = [pos_norm[i] - raw_rest[i] for i in TENDON_PHYSICAL_INDEX]
        thumb_abd_value = pos_norm[THUMB_ABD_PHYSICAL_INDEX] - raw_rest[THUMB_ABD_PHYSICAL_INDEX]
        position_sign = -1.0 if invert_position_obs else 1.0

        obs[:6] = position_sign * np.asarray(tendon_values, dtype=np.float32) * position_gain
        obs[6] = position_sign * float(thumb_abd_value) * thumb_abd_gain
    else:
        raise ValueError(f"Unsupported obs_mode: {obs_mode}")

    if force_obs_source == "current":
        force_vals = []
        force_order = range(7) if obs_mode == "hardware01" else SIM_FORCE_PHYSICAL_INDEX
        for physical_idx in force_order:
            cur = float(curr_ma[physical_idx])
            if not use_signed_current:
                cur = abs(cur)
            force_vals.append(np.tanh(cur / current_scale_ma))
        obs[7:14] = np.asarray(force_vals, dtype=np.float32)
    elif force_obs_source == "zero":
        obs[7:14] = 0.0
    elif force_obs_source == "policy_mean":
        obs[7:14] = force_obs_reference.astype(np.float32)
    elif force_obs_source == "calibrated_current":
        if observation_calibration is None:
            raise ValueError("--force-obs-source calibrated_current requires --observation-calibration")
        obs[7:14] = calibrated_force_proxy(pos_norm, curr_ma, force_obs_reference, observation_calibration)
    else:
        raise ValueError(f"Unsupported force_obs_source: {force_obs_source}")
    obs[14:21] = last_action_obs.astype(np.float32)
    return obs


def z_to_raw_obs(policy: PolicyBundle, z_obs: np.ndarray) -> np.ndarray:
    """Construct raw values whose normalized policy input is z_obs.

    This intentionally avoids pretending that physical normalized actuator units
    equal MuJoCo tendon-length units. The controller exposes physical deviations
    as normalized z-score-like signals and lets the trained normalizer convert
    them into the policy network's expected input scale.
    """
    return policy.obs_mean + z_obs.astype(np.float32) * policy.obs_std


def observation_for_policy(policy: PolicyBundle, obs_values: np.ndarray, obs_mode: str, obs_input_space: str) -> np.ndarray:
    """Convert controller observation values into the raw units expected by infer_action().

    The older tendon_guess adapter intentionally emits z-score-like values
    because the real hand does not expose MuJoCo tendon sensor units.  The newer
    hardware adapter was trained directly on deployable raw signals
    (position proxy, current proxy, last action), so it should bypass that z-score
    reconstruction step.
    """
    mode = obs_input_space
    if mode == "auto":
        mode = "raw" if obs_mode in ("hardware", "hardware01") else "z"
    if mode == "raw":
        return obs_values.astype(np.float32)
    if mode == "z":
        return z_to_raw_obs(policy, obs_values)
    raise ValueError(f"Unsupported obs_input_space: {obs_input_space}")


def safety_violations(curr: list[float], temp: list[float], abort_current: float, abort_temp: float) -> list[str]:
    over_curr = [i for i, value in enumerate(curr) if abs(value) >= abort_current]
    over_temp = [i for i, value in enumerate(temp) if value >= abort_temp]
    if not over_curr and not over_temp:
        return []
    parts = []
    if over_curr:
        parts.append("current " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={curr[i]:.1f}mA" for i in over_curr))
    if over_temp:
        parts.append("temp " + ", ".join(f"{i}:{CHANNEL_NAMES[i]}={temp[i]:.1f}C" for i in over_temp))
    return parts


def enforce_safety(curr: list[float], temp: list[float], abort_current: float, abort_temp: float) -> None:
    parts = safety_violations(curr, temp, abort_current, abort_temp)
    if not parts:
        return
    raise RuntimeError("Safety abort: " + "; ".join(parts))


def enforce_safety_with_confirmation(
    hand: AeroHandController,
    curr: list[float],
    temp: list[float],
    args: argparse.Namespace,
) -> tuple[list[float], list[float]]:
    """Optionally confirm a single over-limit telemetry read before aborting."""
    parts = safety_violations(curr, temp, args.abort_current, args.abort_temp)
    if not parts:
        return curr, temp
    if args.abort_confirm_samples <= 1:
        raise RuntimeError("Safety abort: " + "; ".join(parts))

    reads = [(curr, temp)]
    for _ in range(args.abort_confirm_samples - 1):
        time.sleep(args.abort_confirm_gap)
        next_curr = hand.get_currents_ma()
        next_temp = hand.get_temperatures_c()
        reads.append((next_curr, next_temp))
        next_parts = safety_violations(next_curr, next_temp, args.abort_current, args.abort_temp)
        if not next_parts:
            print(
                "[safety] ignored single over-limit read after confirmation: "
                + "; ".join(parts)
            )
            return next_curr, next_temp

    details = []
    for idx, (read_curr, read_temp) in enumerate(reads):
        read_parts = safety_violations(read_curr, read_temp, args.abort_current, args.abort_temp)
        details.append(f"read{idx}: " + "; ".join(read_parts))
    raise RuntimeError("Safety abort confirmed: " + " | ".join(details))


def log_fieldnames(action_names: list[str] | None = None) -> list[str]:
    if action_names is None:
        action_names = SIM_ACTION_NAMES
    fields = ["timestamp", "elapsed_s", "step", "max_abs_current_ma", "max_temp_c"]
    for idx, name in enumerate(CHANNEL_NAMES):
        fields.extend([f"target_{idx}_{name}", f"pos_{idx}_{name}", f"curr_ma_{idx}_{name}", f"temp_c_{idx}_{name}"])
    for idx, name in enumerate(action_names):
        fields.append(f"policy_action_{idx}_{name}")
    fields.extend([f"obs_z_{idx}" for idx in range(21)])
    return fields


def write_log_row(writer: csv.DictWriter, elapsed: float, step: int, target, pos, curr, temp, action, obs_z, action_names: list[str] | None = None) -> None:
    if action_names is None:
        action_names = SIM_ACTION_NAMES
    row: dict[str, float | int | str] = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "elapsed_s": elapsed,
        "step": step,
        "max_abs_current_ma": max(abs(v) for v in curr),
        "max_temp_c": max(temp),
    }
    for idx, name in enumerate(CHANNEL_NAMES):
        row[f"target_{idx}_{name}"] = target[idx]
        row[f"pos_{idx}_{name}"] = pos[idx]
        row[f"curr_ma_{idx}_{name}"] = curr[idx]
        row[f"temp_c_{idx}_{name}"] = temp[idx]
    for idx, name in enumerate(action_names):
        row[f"policy_action_{idx}_{name}"] = float(action[idx])
    for idx, value in enumerate(obs_z):
        row[f"obs_z_{idx}"] = float(value)
    writer.writerow(row)


def fake_telemetry(
    raw_rest: list[float], observation_calibration: ObservationCalibration | None = None
) -> tuple[list[float], list[float], list[float]]:
    position = list(raw_rest)
    current = (
        baseline_current_ma(position, observation_calibration).astype(float).tolist()
        if observation_calibration is not None
        else [0.0] * 7
    )
    return position, current, [30.0] * 7


def select_position_obs(real_pos: list[float], previous_target: list[float], source: str) -> list[float]:
    if source == "get_pos":
        return real_pos
    if source == "command":
        return previous_target
    raise ValueError(f"Unsupported position observation source: {source}")


def run_controller(args: argparse.Namespace) -> int:
    policy = load_policy(args.policy)
    metadata_path = args.metadata
    if metadata_path == DEFAULT_METADATA and args.policy != DEFAULT_POLICY:
        metadata_path = args.policy.with_name("actor_policy_metadata.json")
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    raw_rest = load_raw_rest(args.calibration)
    max_step_delta = parse_channel_values(args.max_step_delta, args.default_max_step_delta)
    target_bias = parse_channel_values(args.target_bias, 0.0)
    action_gain = parse_channel_values(args.action_gain, 1.0)
    action_sign = parse_channel_overrides(args.action_sign, ACTION_SIGN_BY_PHYSICAL)
    dt = 1.0 / args.rate
    action_mode = args.action_mode
    if action_mode == "auto":
        meta_mode = str(metadata.get("action_mode", "")) + " " + str(metadata.get("actor_observation_type", ""))
        action_mode = "hardware01" if "hardware_01" in meta_mode else "legacy_sim"
    obs_mode = args.obs_mode
    if obs_mode == "auto":
        obs_mode = "hardware01" if action_mode == "hardware01" else "tendon_guess"
    initial_hardware01_u = hardware01_initial_u(policy, args.hardware01_initial_u, raw_rest)
    force_obs_reference = policy.obs_mean[7:14].astype(np.float32)
    observation_calibration = (
        load_observation_calibration(args.observation_calibration)
        if args.force_obs_source == "calibrated_current"
        else None
    )
    last_action_obs = np.asarray(initial_hardware01_u if action_mode == "hardware01" else [0.0] * 7, dtype=np.float32)
    previous_target = list(raw_rest)
    action_log_names = HARDWARE01_ACTION_NAMES if action_mode == "hardware01" else SIM_ACTION_NAMES

    print("Live policy controller")
    print(f"policy: {args.policy}")
    print(f"metadata: {metadata_path}")
    print(f"checkpoint: {metadata.get('checkpoint_root', 'unknown')}")
    print(f"run: {args.run}")
    print(f"rate: {args.rate:.1f} Hz")
    print(f"playback_scale: {args.playback_scale:.3f}")
    print(f"position_gain: {args.position_gain:.3f}; thumb_abd_gain: {args.thumb_abd_gain:.3f}")
    print(f"action_mode: {action_mode}")
    if action_mode == "hardware01":
        print(f"hardware01_initial_u: {args.hardware01_initial_u} -> {fmt(initial_hardware01_u, 3)}")
    print(f"obs_mode: {obs_mode}; hardware_position_scale: {args.hardware_position_scale:.3f}")
    print(f"position_obs_source: {args.position_obs_source}")
    print(f"obs_input_space: {args.obs_input_space}")
    print(f"position_obs_sign: {'inverted' if args.invert_position_obs else 'positive'}")
    print(f"current_scale_ma: {args.current_scale_ma:.1f}; current_mode: {'signed' if args.use_signed_current else 'abs'}")
    print(f"force_obs_source: {args.force_obs_source}")
    if observation_calibration is not None:
        print(f"observation_calibration: {observation_calibration.source_path}")
        print(f"current_residual_scale_ma: {fmt(observation_calibration.residual_scale_ma, 1)}")
    print(f"max_step_delta: {max_step_delta}")
    print(f"action_sign: {action_sign}")
    if any(abs(v) > 1e-12 for v in target_bias):
        print(f"target_bias: {target_bias}")
    if any(abs(v - 1.0) > 1e-12 for v in action_gain):
        print(f"action_gain: {action_gain}")
    if args.abort_confirm_samples > 1:
        print(f"abort_confirm_samples: {args.abort_confirm_samples}; gap={args.abort_confirm_gap:.3f}s")
    print(f"abort_current: {args.abort_current:.1f} mA; abort_temp: {args.abort_temp:.1f} C")

    if not args.run:
        print("\nDry-run only. No serial connection or movement happened.")
        pos, curr, temp = fake_telemetry(raw_rest, observation_calibration)
        if action_mode == "hardware01":
            pos = initial_hardware01_u.tolist()
            if observation_calibration is not None:
                curr = baseline_current_ma(pos, observation_calibration).astype(float).tolist()
            previous_target = pos[:]
        for step in range(min(args.steps, 20)):
            pos_obs = select_position_obs(pos, previous_target, args.position_obs_source)
            obs_z = build_obs(
                pos_obs, curr, last_action_obs, raw_rest,
                args.position_gain, args.thumb_abd_gain, args.current_scale_ma,
                args.use_signed_current, args.force_obs_source, force_obs_reference, observation_calibration,
                args.invert_position_obs, obs_mode, args.hardware_position_scale, action_sign,
            )
            obs_raw = observation_for_policy(policy, obs_z, obs_mode, args.obs_input_space)
            raw_action, _ = infer_action(policy, obs_raw)
            if action_mode == "hardware01":
                action_for_obs = hardware01_u_from_raw_action(raw_action)
                target = physical_from_hardware01_u(action_for_obs, raw_rest, args.playback_scale, action_gain)
            else:
                action_for_obs = raw_action
                target = physical_from_sim_action(raw_action, raw_rest, args.playback_scale, action_gain, action_sign)
            target = apply_target_bias(target, target_bias)
            target = apply_slew(target, previous_target, max_step_delta)
            print(f"[{step:03d}] raw_action={fmt(raw_action, 3)} action_obs={fmt(action_for_obs, 3)} target={fmt(target, 3)} obs={fmt(obs_z[:7], 3)}")
            last_action_obs = action_for_obs
            previous_target = target
            pos = target  # fake closed-loop response for dry-run preview
            if observation_calibration is not None:
                curr = baseline_current_ma(pos, observation_calibration).astype(float).tolist()
        print("\nWhen ready, connect/mount the hand and add --run.")
        return 0

    log_path = args.log or LOG_DIR / f"live_policy_control_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    with log_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=log_fieldnames(action_log_names))
        writer.writeheader()
        with AeroHandController(args.port, args.baud) as hand:
            try:
                rest = hand.apply_rest(args.calibration, settle_s=args.rest_settle)
                previous_target = list(rest)
                if action_mode == "hardware01" and args.hardware01_initial_u != "rest":
                    print(f"[init] ramping to hardware01 initial_u: {fmt(initial_hardware01_u, 3)}")
                    previous_target = ramp_raw_actuators(
                        hand,
                        previous_target,
                        initial_hardware01_u.tolist(),
                        max_step_delta,
                        args.rate,
                        args,
                    )
                    time.sleep(args.rest_settle)
                for step in range(args.steps):
                    loop_start = time.monotonic()
                    pos = hand.get_pos_norm()
                    curr = hand.get_currents_ma()
                    temp = hand.get_temperatures_c()
                    curr, temp = enforce_safety_with_confirmation(hand, curr, temp, args)

                    pos_obs = select_position_obs(pos, previous_target, args.position_obs_source)
                    obs_z = build_obs(
                        pos_obs, curr, last_action_obs, raw_rest,
                        args.position_gain, args.thumb_abd_gain, args.current_scale_ma,
                        args.use_signed_current, args.force_obs_source, force_obs_reference, observation_calibration,
                        args.invert_position_obs, obs_mode, args.hardware_position_scale, action_sign,
                    )
                    obs_raw = observation_for_policy(policy, obs_z, obs_mode, args.obs_input_space)
                    raw_action, _ = infer_action(policy, obs_raw)
                    if action_mode == "hardware01":
                        action_for_obs = hardware01_u_from_raw_action(raw_action)
                        target = physical_from_hardware01_u(action_for_obs, raw_rest, args.playback_scale, action_gain)
                    else:
                        action_for_obs = raw_action
                        target = physical_from_sim_action(raw_action, raw_rest, args.playback_scale, action_gain, action_sign)
                    target = apply_target_bias(target, target_bias)
                    target = apply_slew(target, previous_target, max_step_delta)
                    hand.send_raw_actuators(target)

                    if step % args.sample_every == 0 or step == args.steps - 1:
                        write_log_row(writer, time.monotonic() - started, step, target, pos, curr, temp, action_for_obs, obs_z, action_log_names)
                        file.flush()
                        print(
                            f"[{step:04d}] max_curr={max(abs(v) for v in curr):.1f}mA "
                            f"max_temp={max(temp):.1f}C raw_action={fmt(raw_action, 2)} action_obs={fmt(action_for_obs, 2)} target={fmt(target)} pos={fmt(pos)}"
                        )

                    last_action_obs = action_for_obs
                    previous_target = target
                    elapsed = time.monotonic() - loop_start
                    if elapsed < dt:
                        time.sleep(dt - elapsed)
            except Exception:
                print("\n[recovery] sending raw rest after exception/abort")
                hand.apply_rest(args.calibration, settle_s=args.rest_settle)
                raise

    print(f"\nLive control complete. Log: {log_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the exported RealObs policy in a live real-hand feedback loop.")
    parser.add_argument("--run", action="store_true", help="Actually connect to and move the hand. Omit for dry-run preview.")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION_PATH)
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--rate", type=float, default=12.0, help="Live policy command rate in Hz. Start lower than trace replay.")
    parser.add_argument("--playback-scale", type=float, default=0.35, help="Physical action scale around raw rest.")
    parser.add_argument("--position-gain", type=float, default=2.0, help="Z-score gain for non-thumb actuator position deviations.")
    parser.add_argument("--thumb-abd-gain", type=float, default=2.0, help="Z-score gain for thumb_abd position deviation.")
    parser.add_argument(
        "--obs-mode",
        choices=("auto", "tendon_guess", "hardware", "hardware01"),
        default="auto",
        help="Actor observation adapter. Use hardware01 for policies trained with AeroCubeRotateZAxisHardware01*.",
    )
    parser.add_argument(
        "--position-obs-source",
        choices=("get_pos", "command"),
        default="command",
        help="Position signal fed to the actor. Hardware01 sim trained on commanded ctrl, so command is the default.",
    )
    parser.add_argument(
        "--hardware-position-scale",
        type=float,
        default=1.0,
        help="Scale used to invert physical GET_POS into sim-action-position units for --obs-mode hardware.",
    )
    parser.add_argument(
        "--action-mode",
        choices=("auto", "legacy_sim", "hardware01"),
        default="auto",
        help="How to map policy output to real hand commands. auto uses metadata when available.",
    )
    parser.add_argument(
        "--obs-input-space",
        choices=("auto", "z", "raw"),
        default="auto",
        help="Interpret adapter output as raw policy observations or z-scores. auto uses raw for hardware and z for tendon_guess.",
    )
    parser.add_argument(
        "--invert-position-obs",
        action="store_true",
        help="Map real closing motion to decreasing simulated tendon/joint sensor values.",
    )
    parser.add_argument("--current-scale-ma", type=float, default=2000.0, help="Real current scale for tanh current/load proxy.")
    parser.add_argument("--use-signed-current", action="store_true", help="Use signed current instead of absolute current for force proxy.")
    parser.add_argument(
        "--force-obs-source",
        choices=("current", "zero", "policy_mean", "calibrated_current"),
        default="current",
        help="Force/load observation source. calibrated_current subtracts a no-object spring/friction baseline.",
    )
    parser.add_argument(
        "--observation-calibration",
        type=Path,
        default=DEFAULT_OBSERVATION_CALIBRATION,
        help="Per-channel no-object current baseline JSON for calibrated_current mode.",
    )
    parser.add_argument("--default-max-step-delta", type=float, default=0.06)
    parser.add_argument("--max-step-delta", default="thumb_abd=0.08,thumb_flex=0.06,thumb_tendon=0.06,index=0.06,middle=0.06,ring=0.05,pinky=0.06")
    parser.add_argument(
        "--target-bias",
        default="",
        help="Diagnostic per-channel target offset after policy mapping, e.g. 'thumb_abd=0.25'.",
    )
    parser.add_argument(
        "--action-gain",
        default="",
        help="Diagnostic per-channel multiplier on mapped policy action before rest/bias, e.g. 'thumb_abd=3'.",
    )
    parser.add_argument(
        "--action-sign",
        default="",
        help="Diagnostic per-channel sign override, e.g. 'index=1,ring=1'.",
    )
    parser.add_argument(
        "--hardware01-initial-u",
        choices=("rest", "half", "policy_mean"),
        default="rest",
        help="Initial real-order u pose/last-action seed for Hardware01 policies. policy_mean matches the trained observation distribution better than raw open rest.",
    )
    parser.add_argument("--sample-every", type=int, default=5)
    parser.add_argument("--rest-settle", type=float, default=0.5)
    parser.add_argument("--abort-current", type=float, default=4000.0)
    parser.add_argument("--abort-temp", type=float, default=65.0)
    parser.add_argument("--abort-confirm-samples", type=int, default=1)
    parser.add_argument("--abort-confirm-gap", type=float, default=0.04)
    parser.add_argument("--log", type=Path)
    return run_controller(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
