#!/usr/bin/env python3
"""Native MuJoCo physics sweep for anti-trap exact trace replay."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")

import mediapy as media
import jax
import mujoco
import numpy as np
from mujoco_playground import registry

ENV_NAME = "AeroCubeRotateZAxisHardware01RealCalibratedAntiTrap"
REAL_ORDER = ["thumb_abd", "thumb_flex", "thumb_tendon", "index", "middle", "ring", "pinky"]
SIM_ORDER = ["index", "middle", "ring", "pinky", "thumb_abd", "thumb_flex", "thumb_tendon"]
REAL_TO_SIM = [SIM_ORDER.index(name) for name in REAL_ORDER]
SIM_TO_REAL = [REAL_ORDER.index(name) for name in SIM_ORDER]
DEFAULT_TRACE = Path("analysis/hardware01_real_calibrated_antitrap_trace_20260707/hardware01_antitrap_rollout1_u_trace.json")
DEFAULT_OUT = Path("analysis/physics_id_antitrap_rollout1_native_20260708")

REAL_SCALE = np.asarray([0.21, 0.21, 0.315, 1.35, 1.35, 1.25, 1.20], dtype=np.float64)
REAL_BIAS = np.asarray([-0.12, -0.22, -0.18, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
ACTION_SCALE = np.asarray([0.02, 0.02, 0.02, 0.02, 0.7, 0.003, 0.012], dtype=np.float64)
HOME_CTRL = np.asarray([0.09, 0.09, 0.09, 0.09, 0.75, 0.035, 0.1], dtype=np.float64)
THUMB_U0_CTRL = 0.05
THUMB_U1_CTRL = 1.45


def read_trace(path: Path, max_steps: int | None) -> np.ndarray:
  rows = json.loads(path.read_text())
  arr = np.asarray([r["u_real_order"] for r in rows], dtype=np.float64)
  return arr[:max_steps] if max_steps else arr


def u_real_to_ctrl(u_real_order: np.ndarray, info: dict | None = None) -> np.ndarray:
  u_real_order = np.clip(u_real_order, 0.0, 1.0)
  u_ctrl_real = np.clip(0.5 + (u_real_order - 0.5 - REAL_BIAS) / np.maximum(REAL_SCALE, 1e-6), 0.0, 1.0)
  if info is not None and "action_shape_gamma" in info:
    gamma = np.asarray(info["action_shape_gamma"], dtype=np.float64)
    u_ctrl_real = np.power(np.clip(u_real_order, 1e-6, 1.0), gamma)
  u_sim = u_ctrl_real[SIM_TO_REAL]
  sim_open_ctrl = HOME_CTRL + ACTION_SCALE
  sim_flex_ctrl = HOME_CTRL - ACTION_SCALE
  if info is not None and "action_open_offset" in info:
    sim_open_ctrl = sim_open_ctrl + np.asarray(info["action_open_offset"], dtype=np.float64)
    sim_flex_ctrl = sim_flex_ctrl + np.asarray(info["action_flex_offset"], dtype=np.float64)
  ctrl = sim_open_ctrl + u_sim * (sim_flex_ctrl - sim_open_ctrl)
  thumb_u0 = THUMB_U0_CTRL
  thumb_u1 = THUMB_U1_CTRL
  if info is not None and "thumb_abd_u0_offset" in info:
    thumb_u0 = thumb_u0 + float(info["thumb_abd_u0_offset"])
    thumb_u1 = thumb_u1 + float(info["thumb_abd_u1_offset"])
  thumb_ctrl = thumb_u0 + u_ctrl_real[0] * (thumb_u1 - thumb_u0)
  ctrl[REAL_TO_SIM[0]] = thumb_ctrl
  return ctrl


def geom_ids(model, names):
  return np.asarray([mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, n) for n in names], dtype=np.int32)


def tendon_ids(model, names):
  return np.asarray([mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_TENDON, n) for n in names], dtype=np.int32)


def joint_ids(model, names):
  return np.asarray([mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, n) for n in names], dtype=np.int32)


def body_id(model, name):
  return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)


def set_friction(model, ids, slide):
  model.geom_friction[ids, :] = np.asarray([slide, 0.05, 0.0001])


def scale_position_actuators(model, actuator_ids, scale):
  for aid in actuator_ids:
    kp = model.actuator_gainprm[aid, 0] * scale
    model.actuator_gainprm[aid, 0] = kp
    model.actuator_biasprm[aid, 1] = -kp


def apply_variant(model, name: str):
  cube = geom_ids(model, ["cube"])
  palm = geom_ids(model, [
      "palm_collision_5", "palm_collision_6", "palm_collision_7", "palm_collision_8",
      "palm_collision_9", "palm_collision_10", "palm_collision_11",
  ])
  finger_tips = geom_ids(model, ["if_tip", "mf_tip", "rf_tip", "pf_tip"])
  thumb = geom_ids(model, ["th_mp_collision", "th_bs_collision_1", "th_px_collision_1", "th_tip"])
  all_tips = geom_ids(model, ["if_tip", "mf_tip", "rf_tip", "pf_tip", "th_tip"])
  distal_springs = tendon_ids(model, ["if_spring0", "mf_spring0", "rf_spring0", "pf_spring0", "th_spring1"])
  mcp_springs = tendon_ids(model, ["if_spring1", "mf_spring1", "rf_spring1", "pf_spring1", "th_spring0"])
  params = {}
  if name == "baseline_xml":
    params = {"note": "Raw XML physics."}
  elif name == "train_like_grip":
    set_friction(model, cube, 0.30); set_friction(model, all_tips, 0.80); set_friction(model, palm, 0.25)
    params = {"cube_friction": 0.30, "tip_friction": 0.80, "palm_friction": 0.25}
  elif name == "slippery_cube_palm":
    set_friction(model, cube, 0.12); set_friction(model, all_tips, 0.35); set_friction(model, palm, 0.10)
    params = {"cube_friction": 0.12, "tip_friction": 0.35, "palm_friction": 0.10}
  elif name == "soft_springs":
    model.tendon_stiffness[distal_springs] *= 0.35
    model.tendon_stiffness[mcp_springs] *= 0.50
    model.dof_damping[:] *= 1.35
    params = {"distal_spring_scale": 0.35, "mcp_spring_scale": 0.50, "damping_scale": 1.35}
  elif name == "soft_slippery":
    set_friction(model, cube, 0.12); set_friction(model, all_tips, 0.35); set_friction(model, palm, 0.10)
    model.tendon_stiffness[distal_springs] *= 0.35
    model.tendon_stiffness[mcp_springs] *= 0.50
    model.dof_damping[:] *= 1.35
    params = {"cube_friction": 0.12, "tip_friction": 0.35, "palm_friction": 0.10, "distal_spring_scale": 0.35, "mcp_spring_scale": 0.50}
  elif name == "weak_opposing_fingers":
    set_friction(model, cube, 0.18); set_friction(model, finger_tips, 0.30); set_friction(model, thumb, 0.75)
    scale_position_actuators(model, [0, 1, 2, 3], 0.55)
    params = {"cube_friction": 0.18, "finger_tip_friction": 0.30, "thumb_friction": 0.75, "finger_actuator_kp_scale": 0.55}
  elif name == "thumb_dominant_ejector":
    set_friction(model, cube, 0.14); set_friction(model, finger_tips, 0.25); set_friction(model, thumb, 0.95); set_friction(model, palm, 0.10)
    model.tendon_stiffness[distal_springs] *= 0.40
    scale_position_actuators(model, [0, 1, 2, 3], 0.50)
    params = {"cube_friction": 0.14, "finger_tip_friction": 0.25, "thumb_friction": 0.95, "palm_friction": 0.10, "finger_actuator_kp_scale": 0.50, "distal_spring_scale": 0.40}
  else:
    raise ValueError(name)
  return params


def reset_from_state(model, data, initial_state):
  data.qpos[:] = np.asarray(initial_state.data.qpos, dtype=np.float64)
  data.qvel[:] = np.asarray(initial_state.data.qvel, dtype=np.float64)
  data.ctrl[:] = np.asarray(initial_state.data.ctrl, dtype=np.float64)
  if data.mocap_pos.shape == np.asarray(initial_state.data.mocap_pos).shape:
    data.mocap_pos[:] = np.asarray(initial_state.data.mocap_pos, dtype=np.float64)
    data.mocap_quat[:] = np.asarray(initial_state.data.mocap_quat, dtype=np.float64)
  mujoco.mj_forward(model, data)


def replay(model, u_trace, render_every, height, width, initial_state, info):
  data = mujoco.MjData(model)
  reset_from_state(model, data, initial_state)
  renderer = mujoco.Renderer(model, height=height, width=width)
  camera = "side"
  cube_bid = body_id(model, "cube")
  initial_pos = data.xpos[cube_bid].copy()
  positions = []
  angvels = []
  contact_counts = []
  frames = []
  for step, u in enumerate(u_trace):
    data.ctrl[:] = u_real_to_ctrl(u, info)
    for _ in range(5):
      mujoco.mj_step(model, data)
    positions.append(data.xpos[cube_bid].copy())
    angvels.append(data.cvel[cube_bid, 0:3].copy())
    contact_counts.append(int(data.ncon))
    if step % render_every == 0:
      renderer.update_scene(data, camera=camera)
      frames.append(renderer.render().copy())
  positions = np.asarray(positions)
  angvels = np.asarray(angvels)
  planar = positions[:, :2] - initial_pos[:2]
  planar_norm = np.linalg.norm(planar, axis=1)
  z_ang = np.abs(angvels[:, 2])
  return frames, {
      "steps": int(len(u_trace)),
      "initial_cube_pos": initial_pos.tolist(),
      "final_cube_pos": positions[-1].tolist(),
      "final_planar_delta": (positions[-1, :2] - initial_pos[:2]).tolist(),
      "max_planar_displacement": float(planar_norm.max()),
      "mean_planar_displacement": float(planar_norm.mean()),
      "final_height": float(positions[-1, 2]),
      "min_height": float(positions[:, 2].min()),
      "max_abs_z_angvel": float(z_ang.max()),
      "mean_abs_z_angvel": float(z_ang.mean()),
      "max_contacts": int(max(contact_counts)),
      "mean_contacts": float(np.mean(contact_counts)),
      "ejected_metric": float(planar_norm.max() - 0.45 * z_ang.mean()),
  }


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
  ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
  ap.add_argument("--steps", type=int, default=125)
  ap.add_argument("--render-every", type=int, default=3)
  ap.add_argument("--seed", type=int, default=1)
  ap.add_argument("--rollout-index", type=int, default=1)
  ap.add_argument("--height", type=int, default=720)
  ap.add_argument("--width", type=int, default=960)
  ap.add_argument("--variants", nargs="*", default=["baseline_xml", "train_like_grip", "slippery_cube_palm", "soft_springs", "soft_slippery", "weak_opposing_fingers", "thumb_dominant_ejector"])
  args = ap.parse_args()
  args.out_dir.mkdir(parents=True, exist_ok=True)
  u_trace = read_trace(args.trace, args.steps)
  env = registry.load(ENV_NAME, config=registry.get_default_config(ENV_NAME))
  reset_keys = jax.random.split(jax.random.PRNGKey(args.seed), args.rollout_index + 1)
  initial_state = env.reset(reset_keys[args.rollout_index])
  info = {k: np.asarray(v) for k, v in initial_state.info.items() if k.startswith("action_") or k.startswith("thumb_abd_")}
  xml_text = Path(env.xml_path).read_text()
  assets = env._model_assets
  summaries = []
  for variant in args.variants:
    print(f"=== {variant} ===", flush=True)
    model = mujoco.MjModel.from_xml_string(xml_text, assets=assets)
    params = apply_variant(model, variant)
    frames, metrics = replay(model, u_trace, args.render_every, args.height, args.width, initial_state, info)
    video = args.out_dir / f"{variant}.mp4"
    media.write_video(str(video), frames, fps=20 / args.render_every)
    summary = {"variant": variant, "params": params, "video": str(video), "metrics": metrics}
    (args.out_dir / f"{variant}_metrics.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)
    summaries.append(summary)
  summaries.sort(key=lambda s: s["metrics"]["ejected_metric"], reverse=True)
  ranking = {"env_name": ENV_NAME, "trace": str(args.trace), "order": REAL_ORDER, "summaries": summaries}
  (args.out_dir / "physics_sweep_ranking.json").write_text(json.dumps(ranking, indent=2))
  print("wrote", args.out_dir / "physics_sweep_ranking.json")

if __name__ == "__main__":
  main()
