# Copyright 2025 TetherIA Inc.
# Copyright 2025 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Rotate-z with TetherIA Aero Hand Open."""

from typing import Any, Dict, Optional, Union

import jax
import jax.numpy as jp
from ml_collections import config_dict
from mujoco import mjx
import numpy as np

from mujoco_playground._src import mjx_env
from mujoco_playground._src.manipulation.aero_hand import aero_hand_constants as consts
from mujoco_playground._src.manipulation.aero_hand import base as aero_hand_base


SIM_ORDER = [
    "index",
    "middle",
    "ring",
    "pinky",
    "thumb_abd",
    "thumb_flex",
    "thumb_tendon",
]
REAL_ORDER = [
    "thumb_abd",
    "thumb_flex",
    "thumb_tendon",
    "index",
    "middle",
    "ring",
    "pinky",
]
REAL_TO_SIM = [SIM_ORDER.index(name) for name in REAL_ORDER]
SIM_TO_REAL = [REAL_ORDER.index(name) for name in SIM_ORDER]
HARDWARE_01_ACTION_MODE = "hardware_01_real_order"
HARDWARE_01_RANDOMIZED_ACTION_MODE = "hardware_01_real_order_randomized"
HARDWARE_01_EFFICIENT_ACTION_MODE = "hardware_01_real_order_efficient"
HARDWARE_01_REAL_CALIBRATED_ACTION_MODE = "hardware_01_real_order_real_calibrated"
HARDWARE_01_REAL_CALIBRATED_SMOOTH_ACTION_MODE = "hardware_01_real_order_real_calibrated_smooth"
HARDWARE_01_REAL_CALIBRATED_ANTI_TRAP_ACTION_MODE = "hardware_01_real_order_real_calibrated_anti_trap"
HARDWARE_01_REAL_CALIBRATED_PHYSICS_ID_ACTION_MODE = "hardware_01_real_order_real_calibrated_physics_id"
HARDWARE_01_REAL_TUNED_WINDOW_ACTION_MODE = "hardware_01_real_order_real_tuned_window"



def default_config() -> config_dict.ConfigDict:
  return config_dict.create(
      ctrl_dt=0.05,
      sim_dt=0.01,
      action_scale=[0.02, 0.02, 0.02, 0.02, 0.7, 0.003, 0.012],
      action_mode="sim_delta",
      thumb_abd_u0_ctrl=0.05,
      thumb_abd_u1_ctrl=1.45,
      thumb_abd_flip=False,
      real_command_calibration=False,
      real_command_to_sim_u_scale=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
      real_command_to_sim_u_bias=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
      cube_start_pos=[0.1, 0.0, 0.05],
      cube_start_pos_jitter=[0.01, 0.01, 0.01],
      action_smoothing_max_delta=0.0,
      action_shape_randomization=False,
      action_gamma_min=0.65,
      action_gamma_max=1.45,
      tendon_endpoint_randomization_frac=0.35,
      thumb_abd_endpoint_randomization=0.08,
      action_repeat=1,
      episode_length=500,
      early_termination=True,
      history_len=1,
      include_actuator_force_obs=False,
      hardware_position_obs=False,
      force_obs_scale=100.0,
      force_reward_scale=100.0,
      stalled_angvel_scale=1.0,
      noise_config=config_dict.create(
          level=1.0,
          scales=config_dict.create(
              joint_pos=0.05,
              tendon_length=0.005,
          ),
      ),
      reward_config=config_dict.create(
          scales=config_dict.create(
              angvel=1.0,
              linvel=0.0,
              pose=0.0,
              torques=0.0,
              energy=0.0,
              stalled_force=0.0,
              non_thumb_force=0.0,
              index_ring_participation=0.0,
              middle_pinky_dominance=0.0,
              coordinated_finger_participation=0.0,
              action_magnitude=0.0,
              action_accel=0.0,
              static_clamp=0.0,
              thumb_overcurl=0.0,
              thumb_action_rate=0.0,
              thumb_action_accel=0.0,
              thumb_index_trap=0.0,
              thumb_index_pinch=0.0,
              cube_planar_drift=0.0,
              ring_pocket_trap=0.0,
              tuned_command_window=0.0,
              termination=-100.0,
              action_rate=-1.0,
          ),
      ),
  )


def real_obs_config() -> config_dict.ConfigDict:
  """Config for sim-to-real training with actor-visible real-hand signals only."""
  config = default_config()
  config.include_actuator_force_obs = True

  # Start from the current best mild-transfer smoothness settings, then add
  # bounded force penalties so gripping is useful only when it rotates the cube.
  config.reward_config.scales.action_rate = -2.0
  config.reward_config.scales.energy = -0.0001
  config.reward_config.scales.stalled_force = -0.05
  config.reward_config.scales.non_thumb_force = -0.02
  return config


def real_obs_participation_config() -> config_dict.ConfigDict:
  """RealObs variant nudged toward index/ring participation for sim-to-real."""
  config = real_obs_config()

  # Keep this gentle: reward useful index/ring use and discourage policies that
  # rotate mostly by middle/pinky clamping while index/ring remain idle.
  config.reward_config.scales.index_ring_participation = 0.12
  config.reward_config.scales.middle_pinky_dominance = -0.03
  return config


def hardware_obs_config() -> config_dict.ConfigDict:
  """Actor observes real-hardware-equivalent signals, not MuJoCo tendon sensors."""
  config = real_obs_participation_config()
  config.hardware_position_obs = True
  return config


def hardware_01_real_order_config() -> config_dict.ConfigDict:
  """Hardware-style action variant: real order, u in [0, 1]."""
  config = hardware_obs_config()
  config.action_mode = HARDWARE_01_ACTION_MODE
  # Disabled by default; set e.g. 0.08 to train with real replay-like slew limits.
  config.action_smoothing_max_delta = 0.0
  return config


def hardware_01_randomized_config() -> config_dict.ConfigDict:
  """Hardware-style action variant with randomized sim action-to-joint coupling."""
  config = hardware_01_real_order_config()
  config.action_mode = HARDWARE_01_RANDOMIZED_ACTION_MODE
  config.action_shape_randomization = True
  return config


def hardware_01_efficient_config() -> config_dict.ConfigDict:
  """Hardware-01 policy shaped toward cleaner, coordinated cube spins.

  This variant keeps action-to-joint randomization, but narrows it so the policy
  can learn decisive motions before being asked to survive a very wide family of
  hands.  Additional rewards/penalties discourage high-frequency jitter and
  reward useful thumb/finger coordination only when the cube is actually rotating.
  """
  config = hardware_01_randomized_config()
  config.action_mode = HARDWARE_01_EFFICIENT_ACTION_MODE
  config.action_gamma_min = 0.85
  config.action_gamma_max = 1.20
  config.tendon_endpoint_randomization_frac = 0.15
  config.thumb_abd_endpoint_randomization = 0.04
  config.reward_config.scales.action_rate = -1.5
  config.reward_config.scales.action_accel = -2.0
  config.reward_config.scales.action_magnitude = -0.02
  config.reward_config.scales.coordinated_finger_participation = 0.18
  config.reward_config.scales.index_ring_participation = 0.16
  config.reward_config.scales.middle_pinky_dominance = -0.04
  return config


def hardware_01_real_calibrated_config() -> config_dict.ConfigDict:
  """Hardware-01 variant calibrated to the best real-hand replay range.

  The actor still outputs real-order u in [0, 1], but the MuJoCo command path
  expands that command back to the sim-equivalent range inferred from real-hand
  tests.  This asks training to learn inside the same posture window that was
  physically usable instead of relying on permanent replay-time bias hacks.
  """
  config = hardware_01_efficient_config()
  config.action_mode = HARDWARE_01_REAL_CALIBRATED_ACTION_MODE
  config.real_command_calibration = True
  config.real_command_to_sim_u_scale = [0.21, 0.21, 0.315, 1.35, 1.35, 1.25, 1.20]
  config.real_command_to_sim_u_bias = [-0.12, -0.22, -0.18, 0.0, 0.0, 0.0, 0.0]
  config.cube_start_pos_jitter = [0.02, 0.02, 0.012]
  config.action_gamma_min = 0.75
  config.action_gamma_max = 1.30
  config.tendon_endpoint_randomization_frac = 0.22
  config.thumb_abd_endpoint_randomization = 0.06
  config.reward_config.scales.stalled_force = -0.08
  config.reward_config.scales.non_thumb_force = -0.04
  config.reward_config.scales.static_clamp = -0.08
  config.reward_config.scales.thumb_overcurl = -0.06
  config.reward_config.scales.action_magnitude = -0.015
  config.reward_config.scales.coordinated_finger_participation = 0.20
  config.reward_config.scales.index_ring_participation = 0.18
  return config


def hardware_01_real_calibrated_smooth_config() -> config_dict.ConfigDict:
  """Real-calibrated variant constrained toward hardware-feasible smooth motion.

  The previous real-calibrated run learned some rotation, but relied on fast
  thumb/finger impacts and cube bouncing.  This variant keeps the calibrated
  command window while adding a hard u slew limit, lower effective action
  cadence, stronger smoothness costs, and a cube linear-velocity penalty.
  """
  config = hardware_01_real_calibrated_config()
  config.action_mode = HARDWARE_01_REAL_CALIBRATED_SMOOTH_ACTION_MODE
  config.action_repeat = 2
  config.action_smoothing_max_delta = 0.035
  config.reward_config.scales.action_rate = -3.5
  config.reward_config.scales.action_accel = -6.0
  config.reward_config.scales.thumb_action_rate = -5.0
  config.reward_config.scales.thumb_action_accel = -8.0
  config.reward_config.scales.linvel = -0.18
  config.reward_config.scales.energy = -0.0002
  config.reward_config.scales.stalled_force = -0.10
  config.reward_config.scales.non_thumb_force = -0.05
  config.reward_config.scales.static_clamp = -0.12
  config.reward_config.scales.thumb_overcurl = -0.10
  config.reward_config.scales.action_magnitude = -0.025
  config.reward_config.scales.coordinated_finger_participation = 0.12
  return config


def hardware_01_real_calibrated_anti_trap_config() -> config_dict.ConfigDict:
  """Smooth calibrated variant that discourages thumb-index cube trapping.

  Rollouts from the smooth run rotated the cube but often held it in a tight
  thumb/index pocket.  This variant keeps the hardware-feasible action cadence
  while penalizing geometry and command patterns associated with a static pinch.
  """
  config = hardware_01_real_calibrated_smooth_config()
  config.action_mode = HARDWARE_01_REAL_CALIBRATED_ANTI_TRAP_ACTION_MODE
  config.reward_config.scales.thumb_index_trap = -0.45
  config.reward_config.scales.thumb_index_pinch = -0.28
  config.reward_config.scales.stalled_force = -0.14
  config.reward_config.scales.non_thumb_force = -0.07
  config.reward_config.scales.static_clamp = -0.18
  config.reward_config.scales.thumb_overcurl = -0.16
  config.reward_config.scales.coordinated_finger_participation = 0.04
  config.reward_config.scales.index_ring_participation = 0.10
  config.reward_config.scales.linvel = -0.22
  config.reward_config.scales.action_magnitude = -0.035
  return config


def hardware_01_real_calibrated_physics_id_config() -> config_dict.ConfigDict:
  """Anti-trap variant shaped by the 2026-07-08 sim-real replay failure.

  The real anti-trap trace was electrically safe but the thumb pushed the cube
  laterally off the hand. This variant keeps the anti-trap cadence while adding
  a direct lateral cube-drift cost and slightly stronger anti-ejection pressure
  before any live-policy test is attempted.
  """
  config = hardware_01_real_calibrated_anti_trap_config()
  config.action_mode = HARDWARE_01_REAL_CALIBRATED_PHYSICS_ID_ACTION_MODE
  config.reward_config.scales.cube_planar_drift = -0.80
  config.reward_config.scales.linvel = -0.28
  config.reward_config.scales.thumb_index_pinch = -0.35
  config.reward_config.scales.thumb_overcurl = -0.20
  config.reward_config.scales.coordinated_finger_participation = 0.08
  return config


def hardware_01_real_tuned_window_config() -> config_dict.ConfigDict:
  """PhysicsID follow-up using the operator-tuned real replay command window.

  The best 2026-07-08 hardware replay kept the PhysicsID rollout timing but
  required much lower thumb flex/tendon commands and a high compressed index
  support range.  Train inside that real-working command window instead of
  relying on a replay-time override.
  """
  config = hardware_01_real_calibrated_physics_id_config()
  config.action_mode = HARDWARE_01_REAL_TUNED_WINDOW_ACTION_MODE
  config.real_command_to_sim_u_scale = [0.90, 0.50, 0.60, 0.50, 1.00, 1.00, 1.00]
  config.real_command_to_sim_u_bias = [-0.02, -0.32, -0.14, 0.30, 0.0, 0.0, 0.0]
  config.reward_config.scales.thumb_index_trap = -0.80
  config.reward_config.scales.thumb_index_pinch = -0.55
  config.reward_config.scales.ring_pocket_trap = -0.45
  config.reward_config.scales.tuned_command_window = -0.35
  config.reward_config.scales.cube_planar_drift = -0.95
  config.reward_config.scales.linvel = -0.30
  config.reward_config.scales.thumb_overcurl = -0.28
  config.reward_config.scales.static_clamp = -0.22
  config.reward_config.scales.action_magnitude = -0.025
  config.reward_config.scales.coordinated_finger_participation = 0.05
  config.reward_config.scales.index_ring_participation = 0.06
  return config


class CubeRotateZAxis(aero_hand_base.AeroHandEnv):
  """Rotate a cube around the z-axis as fast as possible wihout dropping it."""

  def __init__(
      self,
      config: config_dict.ConfigDict = default_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(
        xml_path=consts.CUBE_XML.as_posix(),
        config=config,
        config_overrides=config_overrides,
    )
    self._post_init()

  def _post_init(self) -> None:
    self._hand_qids = mjx_env.get_qpos_ids(self.mj_model, consts.JOINT_NAMES)

    self._hand_dqids = mjx_env.get_qvel_ids(self.mj_model, consts.JOINT_NAMES)
    self._cube_qids = mjx_env.get_qpos_ids(self.mj_model, ["cube_freejoint"])
    self._floor_geom_id = self._mj_model.geom("floor").id
    self._cube_geom_id = self._mj_model.geom("cube").id

    home_key = self._mj_model.keyframe("home")
    self._init_q = jp.array(home_key.qpos)
    self._default_pose = self._init_q[self._hand_qids]
    self._lowers, self._uppers = self.mj_model.jnt_range[self._hand_qids].T

    self._init_tendon = jp.array(home_key.ctrl)
    self._default_tendon = self._init_tendon
    force_obs_size = self.mjx_model.nu if self._config.include_actuator_force_obs else 0
    self._actor_obs_size = (
        len(consts.SENSOR_TENDON_NAMES)
        + len(consts.SENSOR_JOINT_NAMES)
        + force_obs_size
        + self.mjx_model.nu
    )

  def _uses_hardware_01_action_mode(self) -> bool:
    return self._config.get("action_mode", "sim_delta") in (
        HARDWARE_01_ACTION_MODE,
        HARDWARE_01_RANDOMIZED_ACTION_MODE,
        HARDWARE_01_EFFICIENT_ACTION_MODE,
        HARDWARE_01_REAL_CALIBRATED_ACTION_MODE,
        HARDWARE_01_REAL_CALIBRATED_SMOOTH_ACTION_MODE,
        HARDWARE_01_REAL_CALIBRATED_ANTI_TRAP_ACTION_MODE,
        HARDWARE_01_REAL_CALIBRATED_PHYSICS_ID_ACTION_MODE,
        HARDWARE_01_REAL_TUNED_WINDOW_ACTION_MODE,
    )

  def _uses_action_shape_randomization(self) -> bool:
    return bool(self._config.get("action_shape_randomization", False))

  def _uses_real_command_calibration(self) -> bool:
    return bool(self._config.get("real_command_calibration", False))

  def _real_command_to_sim_u(self, u_real_order: jax.Array) -> jax.Array:
    if not self._uses_real_command_calibration():
      return u_real_order
    scale = jp.array(self._config.real_command_to_sim_u_scale, dtype=jp.float32)
    bias = jp.array(self._config.real_command_to_sim_u_bias, dtype=jp.float32)
    return jp.clip(0.5 + (u_real_order - 0.5 - bias) / jp.maximum(scale, 1e-6), 0.0, 1.0)

  def _sim_u_to_real_command(self, u_real_order: jax.Array) -> jax.Array:
    if not self._uses_real_command_calibration():
      return u_real_order
    scale = jp.array(self._config.real_command_to_sim_u_scale, dtype=jp.float32)
    bias = jp.array(self._config.real_command_to_sim_u_bias, dtype=jp.float32)
    return jp.clip(0.5 + scale * (u_real_order - 0.5) + bias, 0.0, 1.0)

  def _home_hardware_u(self) -> jax.Array:
    return self._sim_u_to_real_command(jp.ones(self.mjx_model.nu, dtype=jp.float32) * 0.5)

  def _raw_action_to_hardware_u(self, action: jax.Array) -> jax.Array:
    # PPO still emits raw [-1, 1] actions; convert to hardware-style u in [0, 1].
    return jp.clip(0.5 * (action + 1.0), 0.0, 1.0)

  def _hardware_u_real_order_to_ctrl(
      self, u_real_order: jax.Array, info: Optional[dict[str, Any]] = None
  ) -> jax.Array:
    u_real_order = jp.clip(u_real_order, 0.0, 1.0)
    real_to_sim = jp.array(REAL_TO_SIM, dtype=jp.int32)
    sim_to_real = jp.array(SIM_TO_REAL, dtype=jp.int32)

    u_for_ctrl_real_order = self._real_command_to_sim_u(u_real_order)
    if self._uses_action_shape_randomization() and info is not None:
      gamma = info["action_shape_gamma"]
      u_for_ctrl_real_order = jp.power(jp.clip(u_real_order, 1e-6, 1.0), gamma)

    u_sim_order = u_for_ctrl_real_order[sim_to_real]

    action_scale_custom = jp.array(self._config.action_scale, dtype=jp.float32)
    sim_open_ctrl = self._default_tendon + action_scale_custom
    sim_flex_ctrl = self._default_tendon - action_scale_custom
    if self._uses_action_shape_randomization() and info is not None:
      sim_open_ctrl = sim_open_ctrl + info["action_open_offset"]
      sim_flex_ctrl = sim_flex_ctrl + info["action_flex_offset"]
    motor_targets = sim_open_ctrl + u_sim_order * (sim_flex_ctrl - sim_open_ctrl)

    thumb_u = u_for_ctrl_real_order[0]
    if self._config.get("thumb_abd_flip", False):
      thumb_u = 1.0 - thumb_u
    thumb_u0_ctrl = self._config.thumb_abd_u0_ctrl
    thumb_u1_ctrl = self._config.thumb_abd_u1_ctrl
    if self._uses_action_shape_randomization() and info is not None:
      thumb_u0_ctrl = thumb_u0_ctrl + info["thumb_abd_u0_offset"]
      thumb_u1_ctrl = thumb_u1_ctrl + info["thumb_abd_u1_offset"]
    thumb_abd_ctrl = thumb_u0_ctrl + thumb_u * (thumb_u1_ctrl - thumb_u0_ctrl)
    motor_targets = motor_targets.at[real_to_sim[0]].set(thumb_abd_ctrl)
    return motor_targets

  def _ctrl_to_hardware_u_real_order(self, ctrl: jax.Array) -> jax.Array:
    action_scale_custom = jp.array(self._config.action_scale, dtype=jp.float32)
    sim_open_ctrl = self._default_tendon + action_scale_custom
    sim_flex_ctrl = self._default_tendon - action_scale_custom
    denom = sim_flex_ctrl - sim_open_ctrl
    u_sim_order = (ctrl - sim_open_ctrl) / denom

    real_to_sim = jp.array(REAL_TO_SIM, dtype=jp.int32)
    u_real_order = u_sim_order[real_to_sim]

    thumb_denom = self._config.thumb_abd_u1_ctrl - self._config.thumb_abd_u0_ctrl
    thumb_u = (ctrl[real_to_sim[0]] - self._config.thumb_abd_u0_ctrl) / thumb_denom
    if self._config.get("thumb_abd_flip", False):
      thumb_u = 1.0 - thumb_u
    u_real_order = u_real_order.at[0].set(thumb_u)
    u_real_order = self._sim_u_to_real_command(u_real_order)
    return jp.clip(u_real_order, 0.0, 1.0)

  def _action_to_ctrl_and_last_action(
      self, action: jax.Array, info: dict[str, Any]
  ) -> tuple[jax.Array, jax.Array]:
    if not self._uses_hardware_01_action_mode():
      action_scale_custom = jp.array(self._config.action_scale, dtype=jp.float32)
      return self._default_tendon + action * action_scale_custom, action

    u_real_order = self._raw_action_to_hardware_u(action)
    max_delta = self._config.get("action_smoothing_max_delta", 0.0)
    if max_delta and max_delta > 0.0:
      previous_u = info["last_act"]
      u_real_order = previous_u + jp.clip(u_real_order - previous_u, -max_delta, max_delta)
    return self._hardware_u_real_order_to_ctrl(u_real_order, info), u_real_order

  def reset(self, rng: jax.Array) -> mjx_env.State:
    # Randomize hand qpos and qvel.
    rng, pos_rng, vel_rng = jax.random.split(rng, 3)
    q_hand = jp.clip(
        self._default_pose + 0.1 * jax.random.normal(pos_rng, (consts.NQ,)),
        self._lowers,
        self._uppers,
    )
    v_hand = 0.0 * jax.random.normal(vel_rng, (consts.NV,))

    # Randomize cube qpos and qvel.
    rng, p_rng, quat_rng = jax.random.split(rng, 3)
    cube_start_pos = jp.array(self._config.cube_start_pos, dtype=jp.float32)
    cube_start_jitter = jp.array(self._config.cube_start_pos_jitter, dtype=jp.float32)
    start_pos = cube_start_pos + jax.random.uniform(
        p_rng, (3,), minval=-cube_start_jitter, maxval=cube_start_jitter
    )
    start_quat = aero_hand_base.uniform_quat(quat_rng)
    q_cube = jp.array([*start_pos, *start_quat])
    v_cube = jp.zeros(6)

    qpos = jp.concatenate([q_hand, q_cube])
    qvel = jp.concatenate([v_hand, v_cube])
    data = mjx_env.make_data(
        self.mj_model,
        qpos=qpos,
        qvel=qvel,
        ctrl=self._default_tendon,  # Change: only use the control tendons
        mocap_pos=jp.array([-100, -100, -100]),  # Hide goal for this task.
    )

    last_action = (
        self._home_hardware_u()
        if self._uses_hardware_01_action_mode()
        else jp.zeros(self.mjx_model.nu)
    )
    action_shape_gamma = jp.ones(self.mjx_model.nu, dtype=jp.float32)
    action_open_offset = jp.zeros(self.mjx_model.nu, dtype=jp.float32)
    action_flex_offset = jp.zeros(self.mjx_model.nu, dtype=jp.float32)
    thumb_abd_u0_offset = jp.array(0.0, dtype=jp.float32)
    thumb_abd_u1_offset = jp.array(0.0, dtype=jp.float32)
    if self._uses_action_shape_randomization():
      rng, gamma_rng, open_rng, flex_rng, thumb_rng = jax.random.split(rng, 5)
      action_shape_gamma = jax.random.uniform(
          gamma_rng,
          (self.mjx_model.nu,),
          minval=self._config.action_gamma_min,
          maxval=self._config.action_gamma_max,
      )
      endpoint_span = (
          jp.array(self._config.action_scale, dtype=jp.float32)
          * self._config.tendon_endpoint_randomization_frac
      )
      action_open_offset = jax.random.uniform(
          open_rng, (self.mjx_model.nu,), minval=-1.0, maxval=1.0
      ) * endpoint_span
      action_flex_offset = jax.random.uniform(
          flex_rng, (self.mjx_model.nu,), minval=-1.0, maxval=1.0
      ) * endpoint_span
      # Thumb abduction is not a tendon channel in the hardware-style mapping,
      # so randomize its explicit endpoints separately in ctrl units.
      thumb_offsets = jax.random.uniform(
          thumb_rng, (2,), minval=-1.0, maxval=1.0
      ) * self._config.thumb_abd_endpoint_randomization
      thumb_abd_u0_offset = thumb_offsets[0]
      thumb_abd_u1_offset = thumb_offsets[1]
    info = {
        "rng": rng,
        "last_act": last_action,
        "last_last_act": last_action,
        "motor_targets": data.ctrl,
        "last_cube_angvel": jp.zeros(3),
        "action_shape_gamma": action_shape_gamma,
        "action_open_offset": action_open_offset,
        "action_flex_offset": action_flex_offset,
        "thumb_abd_u0_offset": thumb_abd_u0_offset,
        "thumb_abd_u1_offset": thumb_abd_u1_offset,
    }

    metrics = {}
    for k in self._config.reward_config.scales.keys():
      metrics[f"reward/{k}"] = jp.zeros(())

    obs_history = jp.zeros(self._config.history_len * self._actor_obs_size)
    obs = self._get_obs(data, info, obs_history)
    reward, done = jp.zeros(2)  # pylint: disable=redefined-outer-name
    return mjx_env.State(data, obs, reward, done, metrics, info)

  def step(self, state: mjx_env.State, action: jax.Array) -> mjx_env.State:

    motor_targets, action_for_obs = self._action_to_ctrl_and_last_action(
        action, state.info
    )
    data = mjx_env.step(
        self.mjx_model, state.data, motor_targets, self.n_substeps
    )
    state.info["motor_targets"] = motor_targets

    obs = self._get_obs(data, state.info, state.obs["state"])
    done = self._get_termination(data)

    rewards = self._get_reward(data, action_for_obs, state.info, state.metrics, done)
    rewards = {
        k: v * self._config.reward_config.scales[k] for k, v in rewards.items()
    }
    reward = sum(rewards.values()) * self.dt  # pylint: disable=redefined-outer-name

    state.info["last_last_act"] = state.info["last_act"]
    state.info["last_act"] = action_for_obs
    state.info["last_cube_angvel"] = self.get_cube_angvel(data)
    for k, v in rewards.items():
      state.metrics[f"reward/{k}"] = v

    done = done.astype(reward.dtype)
    state = state.replace(data=data, obs=obs, reward=reward, done=done)
    return state

  def _get_termination(self, data: mjx.Data) -> jax.Array:
    fall_termination = self.get_cube_position(data)[2] < -0.05
    return fall_termination

  def _get_obs(
      self, data: mjx.Data, info: dict[str, Any], obs_history: jax.Array
  ) -> Dict[str, jax.Array]:

    info["rng"], noise_rng = jax.random.split(info["rng"])

    # ------- tendon length sensor -------
    tendon_lengths = jp.zeros(
        (len(consts.SENSOR_TENDON_NAMES),), dtype=jp.float32
    )
    for idx, name in enumerate(consts.SENSOR_TENDON_NAMES):
      v = mjx_env.get_sensor_data(self.mj_model, data, name)
      v = jp.ravel(v)[0]
      tendon_lengths = tendon_lengths.at[idx].set(v)

    info["rng"], noise_rng = jax.random.split(info["rng"])
    noisy_tendon_lengths = (
        tendon_lengths
        + (2 * jax.random.uniform(noise_rng, shape=tendon_lengths.shape) - 1)
        * self._config.noise_config.level
        * self._config.noise_config.scales.tendon_length
    )

    # ------- joint angle sensor -------
    joint_angles = jp.zeros((len(consts.SENSOR_JOINT_NAMES),), dtype=jp.float32)
    for idx, name in enumerate(consts.SENSOR_JOINT_NAMES):
      v = mjx_env.get_sensor_data(self.mj_model, data, name)
      v = jp.ravel(v)[0]
      joint_angles = joint_angles.at[idx].set(v)

    info["rng"], noise_rng = jax.random.split(info["rng"])
    noisy_joint_angles = (
        joint_angles
        + (2 * jax.random.uniform(noise_rng, shape=joint_angles.shape) - 1)
        * self._config.noise_config.level
        * self._config.noise_config.scales.joint_pos
    )

    if self._config.get("hardware_position_obs", False):
      # Real hand deployability path: GET_POS gives normalized actuator/servo
      # positions.  In hardware_01 mode, expose the same real-order u in [0, 1]
      # that the actor commands; old variants keep the legacy sim-order proxy.
      if self._uses_hardware_01_action_mode():
        hardware_position_proxy = self._ctrl_to_hardware_u_real_order(data.ctrl)
      else:
        action_scale_custom = jp.array(self._config.action_scale, dtype=jp.float32)
        hardware_position_proxy = (data.ctrl - self._default_tendon) / action_scale_custom
      state_parts = [hardware_position_proxy]
    else:
      state_parts = [noisy_tendon_lengths, noisy_joint_angles]
    if self._config.include_actuator_force_obs:
      actuator_force_proxy = jp.tanh(data.actuator_force / self._config.force_obs_scale)
      if self._uses_hardware_01_action_mode():
        # Real GET_CURR arrives in REAL_ORDER, so actor-visible force/current
        # proxy should use the same order as hardware_position_proxy and last_act.
        actuator_force_proxy = actuator_force_proxy[jp.array(REAL_TO_SIM, dtype=jp.int32)]
      state_parts.append(actuator_force_proxy)
    state_parts.append(info["last_act"])
    state = jp.concatenate(state_parts)

    joint_angles = data.qpos[self._hand_qids]
    info["rng"], noise_rng = jax.random.split(info["rng"])
    obs_history = jp.roll(obs_history, state.size)
    obs_history = obs_history.at[: state.size].set(state)

    cube_pos = self.get_cube_position(data)
    palm_pos = self.get_palm_position(data)
    cube_pos_error = palm_pos - cube_pos
    cube_quat = self.get_cube_orientation(data)
    cube_angvel = self.get_cube_angvel(data)
    cube_linvel = self.get_cube_linvel(data)
    fingertip_positions = self.get_fingertip_positions(data)
    joint_torques = data.actuator_force

    privileged_state = jp.concatenate([
        state,
        joint_angles,
        data.qvel[self._hand_dqids],
        joint_torques,
        fingertip_positions,
        cube_pos_error,
        cube_quat,
        cube_angvel,
        cube_linvel,
    ])

    return {
        "state": obs_history,
        "privileged_state": privileged_state,
    }

  def _get_reward(
      self,
      data: mjx.Data,
      action: jax.Array,
      info: dict[str, Any],
      metrics: dict[str, Any],
      done: jax.Array,
  ) -> dict[str, jax.Array]:
    del metrics  # Unused.
    cube_pos = self.get_cube_position(data)
    palm_pos = self.get_palm_position(data)
    cube_pos_error = palm_pos - cube_pos
    cube_angvel = self.get_cube_angvel(data)
    cube_linvel = self.get_cube_linvel(data)
    return {
        "angvel": self._reward_angvel(cube_angvel, cube_pos_error),
        "linvel": self._cost_linvel(cube_linvel),
        "termination": done,
        "action_rate": self._cost_action_rate(
            action, info["last_act"], info["last_last_act"]
        ),
        "pose": self._cost_pose(data.qpos[self._hand_qids]),
        "torques": self._cost_torques(data.actuator_force),
        "energy": self._cost_energy(
            data.qvel[self._hand_dqids], data.qfrc_actuator[self._hand_dqids]
        ),
        "stalled_force": self._cost_stalled_force(data.actuator_force, cube_angvel),
        "non_thumb_force": self._cost_non_thumb_force(data.actuator_force, cube_angvel),
        "index_ring_participation": self._reward_index_ring_participation(action, cube_angvel),
        "middle_pinky_dominance": self._cost_middle_pinky_dominance(action, cube_angvel),
        "coordinated_finger_participation": self._reward_coordinated_finger_participation(action, cube_angvel),
        "action_magnitude": self._cost_action_magnitude(action),
        "action_accel": self._cost_action_accel(action, info["last_act"], info["last_last_act"]),
        "static_clamp": self._cost_static_clamp(action, cube_angvel),
        "thumb_overcurl": self._cost_thumb_overcurl(action, cube_angvel),
        "thumb_action_rate": self._cost_thumb_action_rate(action, info["last_act"]),
        "thumb_action_accel": self._cost_thumb_action_accel(action, info["last_act"], info["last_last_act"]),
        "thumb_index_trap": self._cost_thumb_index_trap(data, action, cube_angvel),
        "thumb_index_pinch": self._cost_thumb_index_pinch(action, cube_angvel),
        "cube_planar_drift": self._cost_cube_planar_drift(cube_pos, palm_pos, cube_angvel),
        "ring_pocket_trap": self._cost_ring_pocket_trap(data, cube_angvel),
        "tuned_command_window": self._cost_tuned_command_window(action, cube_angvel),
    }

  def _cost_torques(self, torques: jax.Array) -> jax.Array:
    return jp.sum(jp.square(torques))

  def _force_proxy_abs(self, actuator_force: jax.Array) -> jax.Array:
    return jp.tanh(jp.abs(actuator_force) / self._config.force_reward_scale)

  def _low_rotation_gate(self, cube_angvel: jax.Array) -> jax.Array:
    return jp.exp(-jp.abs(cube_angvel[2]) / self._config.stalled_angvel_scale)

  def _cost_stalled_force(
      self, actuator_force: jax.Array, cube_angvel: jax.Array
  ) -> jax.Array:
    force_proxy = self._force_proxy_abs(actuator_force)
    return jp.sum(jp.square(force_proxy)) * self._low_rotation_gate(cube_angvel)

  def _cost_non_thumb_force(
      self, actuator_force: jax.Array, cube_angvel: jax.Array
  ) -> jax.Array:
    # Tendon channels 0..3 are index/middle/ring/pinky. These are the
    # channels most likely to jam the cube against the palm in the real hand.
    non_thumb_force_proxy = self._force_proxy_abs(actuator_force[:4])
    return jp.sum(jp.square(non_thumb_force_proxy)) * self._low_rotation_gate(cube_angvel)

  def _cost_static_clamp(self, action: jax.Array, cube_angvel: jax.Array) -> jax.Array:
    if not self._uses_hardware_01_action_mode():
      return jp.zeros(())
    fingers = jp.take(action, jp.array([3, 4, 5, 6], dtype=jp.int32))
    clamp = jp.mean(jp.square(jp.maximum(fingers - 0.70, 0.0)))
    return clamp * self._low_rotation_gate(cube_angvel)

  def _cost_thumb_overcurl(self, action: jax.Array, cube_angvel: jax.Array) -> jax.Array:
    if not self._uses_hardware_01_action_mode():
      return jp.zeros(())
    thumb = jp.take(action, jp.array([0, 1, 2], dtype=jp.int32))
    thresholds = jp.array([0.56, 0.46, 0.60], dtype=jp.float32)
    overcurl = jp.mean(jp.square(jp.maximum(thumb - thresholds, 0.0)))
    return overcurl * self._low_rotation_gate(cube_angvel)

  def _rotation_usefulness_gate(self, cube_angvel: jax.Array) -> jax.Array:
    return jp.tanh(jp.abs(cube_angvel[2]) / 1.0)

  def _closing_action(self, action: jax.Array) -> jax.Array:
    if self._uses_hardware_01_action_mode():
      # Hardware real order: [thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky].
      return jp.take(action, jp.array([3, 4, 5, 6], dtype=jp.int32))
    # Legacy sim-order behavior is intentionally preserved for existing envs.
    return jp.maximum(action[:4], 0.0)

  def _reward_index_ring_participation(
      self, action: jax.Array, cube_angvel: jax.Array
  ) -> jax.Array:
    closing = self._closing_action(action)
    index_ring = 0.5 * (closing[0] + closing[2])
    return jp.tanh(2.0 * index_ring) * self._rotation_usefulness_gate(cube_angvel)

  def _cost_middle_pinky_dominance(
      self, action: jax.Array, cube_angvel: jax.Array
  ) -> jax.Array:
    closing = self._closing_action(action)
    index_ring = 0.5 * (closing[0] + closing[2])
    middle_pinky = 0.5 * (closing[1] + closing[3])
    dominance = jp.maximum(middle_pinky - index_ring - 0.15, 0.0)
    return jp.square(dominance) * self._rotation_usefulness_gate(cube_angvel)

  def _reward_coordinated_finger_participation(
      self, action: jax.Array, cube_angvel: jax.Array
  ) -> jax.Array:
    if not self._uses_hardware_01_action_mode():
      return jp.zeros(())
    # Real order: [thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky].
    thumb_activity = jp.mean(jp.abs(action[:3] - 0.5))
    nonthumb_closing = jp.mean(jp.take(action, jp.array([3, 4, 5, 6], dtype=jp.int32)))
    coordinated = jp.sqrt(jp.maximum(thumb_activity * nonthumb_closing, 0.0))
    return jp.tanh(3.0 * coordinated) * self._rotation_usefulness_gate(cube_angvel)

  def _cost_thumb_action_rate(self, act: jax.Array, last_act: jax.Array) -> jax.Array:
    if not self._uses_hardware_01_action_mode():
      return jp.zeros(())
    return jp.sum(jp.square(act[:3] - last_act[:3]))

  def _cost_thumb_action_accel(
      self, act: jax.Array, last_act: jax.Array, last_last_act: jax.Array
  ) -> jax.Array:
    if not self._uses_hardware_01_action_mode():
      return jp.zeros(())
    return jp.sum(jp.square(act[:3] - 2.0 * last_act[:3] + last_last_act[:3]))

  def _cost_thumb_index_trap(
      self, data: mjx.Data, action: jax.Array, cube_angvel: jax.Array
  ) -> jax.Array:
    if not self._uses_hardware_01_action_mode():
      return jp.zeros(())
    del action  # Geometry-only trap signal; command pinch is handled separately.
    fingertips = self.get_fingertip_positions(data).reshape((5, 3))
    index_tip = fingertips[0]
    thumb_tip = fingertips[4]
    cube_pos = self.get_cube_position(data)
    index_cube_dist = jp.linalg.norm(index_tip - cube_pos)
    thumb_cube_dist = jp.linalg.norm(thumb_tip - cube_pos)
    thumb_index_gap = jp.linalg.norm(thumb_tip - index_tip)
    sigma_cube = 0.055
    sigma_gap = 0.090
    both_on_cube = jp.exp(
        -(jp.square(index_cube_dist) + jp.square(thumb_cube_dist))
        / (2.0 * sigma_cube * sigma_cube)
    )
    tight_gap = jp.exp(-jp.square(thumb_index_gap) / (2.0 * sigma_gap * sigma_gap))
    return both_on_cube * tight_gap * self._low_rotation_gate(cube_angvel)

  def _cost_thumb_index_pinch(
      self, action: jax.Array, cube_angvel: jax.Array
  ) -> jax.Array:
    if not self._uses_hardware_01_action_mode():
      return jp.zeros(())
    # Real order: [thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky].
    thumb_closure = 0.5 * (action[1] + action[2])
    index_closure = action[3]
    pinch = jp.maximum(thumb_closure - 0.48, 0.0) * jp.maximum(index_closure - 0.55, 0.0)
    return jp.square(pinch) * self._low_rotation_gate(cube_angvel)

  def _cost_action_magnitude(self, action: jax.Array) -> jax.Array:
    if self._uses_hardware_01_action_mode():
      return jp.mean(jp.square(action - self._home_hardware_u()))
    return jp.mean(jp.square(action))

  def _cost_tuned_command_window(
      self, action: jax.Array, cube_angvel: jax.Array
  ) -> jax.Array:
    if self._config.get("action_mode") != HARDWARE_01_REAL_TUNED_WINDOW_ACTION_MODE:
      return jp.zeros(())
    # Real-order u: [thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky].
    thumb_flex_over = jp.square(jp.maximum(action[1] - 0.34, 0.0))
    thumb_tendon_over = jp.square(jp.maximum(action[2] - 0.52, 0.0))
    index_under = jp.square(jp.maximum(0.58 - action[3], 0.0))
    index_over = 0.25 * jp.square(jp.maximum(action[3] - 0.94, 0.0))
    return (thumb_flex_over + thumb_tendon_over + index_under + index_over) * (
        0.25 + 0.75 * self._low_rotation_gate(cube_angvel)
    )

  def _cost_action_accel(
      self, act: jax.Array, last_act: jax.Array, last_last_act: jax.Array
  ) -> jax.Array:
    return jp.mean(jp.square(act - 2.0 * last_act + last_last_act))

  def _cost_energy(
      self, qvel: jax.Array, qfrc_actuator: jax.Array
  ) -> jax.Array:
    return jp.sum(
        jp.abs(qvel) * jp.abs(qfrc_actuator)
    )  # Change: only use the control joints


  def _cost_cube_planar_drift(
      self, cube_pos: jax.Array, palm_pos: jax.Array, cube_angvel: jax.Array
  ) -> jax.Array:
    # Penalize lateral displacement from the palm, especially when the cube is
    # not producing useful z rotation. This targets the real replay failure
    # where the thumb pushed the cube sideways off the hand.
    planar_error = jp.linalg.norm((cube_pos - palm_pos)[:2])
    return planar_error * (0.35 + 0.65 * self._low_rotation_gate(cube_angvel))

  def _cost_ring_pocket_trap(
      self, data: mjx.Data, cube_angvel: jax.Array
  ) -> jax.Array:
    if not self._uses_hardware_01_action_mode():
      return jp.zeros(())
    fingertips = self.get_fingertip_positions(data).reshape((5, 3))
    ring_tip = fingertips[2]
    pinky_tip = fingertips[3]
    cube_pos = self.get_cube_position(data)
    palm_pos = self.get_palm_position(data)
    ring_cube_dist = jp.linalg.norm(ring_tip - cube_pos)
    pinky_cube_dist = jp.linalg.norm(pinky_tip - cube_pos)
    palm_cube_dist = jp.linalg.norm(palm_pos - cube_pos)
    ring_near = jp.exp(-jp.square(ring_cube_dist) / (2.0 * 0.060 * 0.060))
    pinky_near = jp.exp(-jp.square(pinky_cube_dist) / (2.0 * 0.075 * 0.075))
    palm_near = jp.exp(-jp.square(palm_cube_dist) / (2.0 * 0.095 * 0.095))
    return ring_near * (0.5 + 0.5 * pinky_near) * palm_near * self._low_rotation_gate(cube_angvel)

  def _cost_linvel(self, cube_linvel: jax.Array) -> jax.Array:
    return jp.linalg.norm(cube_linvel, ord=1, axis=-1)

  def _reward_angvel(
      self, cube_angvel: jax.Array, cube_pos_error: jax.Array
  ) -> jax.Array:
    # Unconditionally maximize angvel in the z-direction.
    del cube_pos_error  # Unused.
    return cube_angvel @ jp.array([0.0, 0.0, 1.0])

  def _cost_action_rate(
      self, act: jax.Array, last_act: jax.Array, last_last_act: jax.Array
  ) -> jax.Array:
    del last_last_act  # Unused.
    return jp.sum(jp.square(act - last_act))

  def _cost_pose(self, joint_angles: jax.Array) -> jax.Array:
    return jp.sum(jp.square(joint_angles - self._default_pose))


def domain_randomize_physics_id(
    model: mjx.Model, rng: jax.Array):
  """Wider randomization for the real thumb-ejection failure mode.

  The 2026-07-08 exact trace replay was safe, but the thumb pushed the cube
  laterally off the real hand. This randomizer keeps the existing base
  randomization and adds per-env variation for palm/cube friction, thumb-vs-
  finger contact balance, tendon spring stiffness, and weak opposing fingers.
  """
  mj_model = CubeRotateZAxis().mj_model
  cube_geom_id = mj_model.geom("cube").id
  palm_geom_ids = np.array([
      mj_model.geom(n).id for n in [
          "palm_collision_5", "palm_collision_6", "palm_collision_7",
          "palm_collision_8", "palm_collision_9", "palm_collision_10",
          "palm_collision_11",
      ]
  ])
  finger_tip_geom_ids = np.array([mj_model.geom(n).id for n in ["if_tip", "mf_tip", "rf_tip", "pf_tip"]])
  thumb_geom_ids = np.array([mj_model.geom(n).id for n in ["th_mp_collision", "th_bs_collision_1", "th_px_collision_1", "th_tip"]])
  distal_spring_ids = np.array([mj_model.tendon(n).id for n in ["if_spring0", "mf_spring0", "rf_spring0", "pf_spring0", "th_spring1"]])
  mcp_spring_ids = np.array([mj_model.tendon(n).id for n in ["if_spring1", "mf_spring1", "rf_spring1", "pf_spring1", "th_spring0"]])
  finger_actuator_ids = jp.array([0, 1, 2, 3], dtype=jp.int32)
  thumb_actuator_ids = jp.array([4, 5, 6], dtype=jp.int32)

  model, in_axes = domain_randomize(model, rng)

  @jax.vmap
  def rand_extra(rng, geom_friction, tendon_stiffness, actuator_gainprm, actuator_biasprm):
    rng, cube_key, finger_key, thumb_key, palm_key = jax.random.split(rng, 5)
    cube_friction = jax.random.uniform(cube_key, (), minval=0.10, maxval=0.45)
    finger_friction = jax.random.uniform(finger_key, (), minval=0.20, maxval=0.90)
    thumb_friction = jax.random.uniform(thumb_key, (), minval=0.45, maxval=1.15)
    palm_friction = jax.random.uniform(palm_key, (), minval=0.08, maxval=0.30)
    geom_friction = geom_friction.at[cube_geom_id, 0].set(cube_friction)
    geom_friction = geom_friction.at[finger_tip_geom_ids, 0].set(finger_friction)
    geom_friction = geom_friction.at[thumb_geom_ids, 0].set(thumb_friction)
    geom_friction = geom_friction.at[palm_geom_ids, 0].set(palm_friction)

    rng, distal_key, mcp_key = jax.random.split(rng, 3)
    distal_scale = jax.random.uniform(distal_key, (), minval=0.30, maxval=1.10)
    mcp_scale = jax.random.uniform(mcp_key, (), minval=0.40, maxval=1.10)
    tendon_stiffness = tendon_stiffness.at[distal_spring_ids].multiply(distal_scale)
    tendon_stiffness = tendon_stiffness.at[mcp_spring_ids].multiply(mcp_scale)

    rng, finger_kp_key, thumb_kp_key = jax.random.split(rng, 3)
    finger_kp_scale = jax.random.uniform(finger_kp_key, (), minval=0.45, maxval=1.10)
    thumb_kp_scale = jax.random.uniform(thumb_kp_key, (), minval=0.75, maxval=1.20)
    finger_kp = actuator_gainprm[finger_actuator_ids, 0] * finger_kp_scale
    thumb_kp = actuator_gainprm[thumb_actuator_ids, 0] * thumb_kp_scale
    actuator_gainprm = actuator_gainprm.at[finger_actuator_ids, 0].set(finger_kp)
    actuator_gainprm = actuator_gainprm.at[thumb_actuator_ids, 0].set(thumb_kp)
    actuator_biasprm = actuator_biasprm.at[finger_actuator_ids, 1].set(-finger_kp)
    actuator_biasprm = actuator_biasprm.at[thumb_actuator_ids, 1].set(-thumb_kp)
    return geom_friction, tendon_stiffness, actuator_gainprm, actuator_biasprm

  batched_tendon_stiffness = jp.repeat(model.tendon_stiffness[None, :], rng.shape[0], axis=0)
  geom_friction, tendon_stiffness, actuator_gainprm, actuator_biasprm = rand_extra(
      rng, model.geom_friction, batched_tendon_stiffness, model.actuator_gainprm, model.actuator_biasprm
  )
  model = model.tree_replace({
      "geom_friction": geom_friction,
      "tendon_stiffness": tendon_stiffness,
      "actuator_gainprm": actuator_gainprm,
      "actuator_biasprm": actuator_biasprm,
  })
  in_axes = in_axes.tree_replace({
      "geom_friction": 0,
      "tendon_stiffness": 0,
      "actuator_gainprm": 0,
      "actuator_biasprm": 0,
  })
  return model, in_axes


class CubeRotateZAxisRealObs(CubeRotateZAxis):
  """Cube rotation variant whose actor observes deployable hand signals only."""

  def __init__(
      self,
      config: config_dict.ConfigDict = real_obs_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config=config, config_overrides=config_overrides)


class CubeRotateZAxisRealObsParticipation(CubeRotateZAxis):
  """RealObs variant with gentle index/ring participation shaping."""

  def __init__(
      self,
      config: config_dict.ConfigDict = real_obs_participation_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config=config, config_overrides=config_overrides)


class CubeRotateZAxisHardwareObs(CubeRotateZAxis):
  """Actor-observation variant aligned to physical GET_POS/GET_CURR control."""

  def __init__(
      self,
      config: config_dict.ConfigDict = hardware_obs_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config=config, config_overrides=config_overrides)


class CubeRotateZAxisHardware01RealOrder(CubeRotateZAxis):
  """Hardware-style action variant in real hand order.

  PPO raw actions are converted from [-1, 1] to u in [0, 1], ordered as
  [thumb_abd, thumb_flex, thumb_tendon, index, middle, ring, pinky].
  Tendon u=0 opens/releases, u=1 curls/contacts.
  """

  def __init__(
      self,
      config: config_dict.ConfigDict = hardware_01_real_order_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config=config, config_overrides=config_overrides)


class CubeRotateZAxisHardware01Randomized(CubeRotateZAxis):
  """Hardware-style action variant with randomized action-to-joint coupling.

  The actor still commands real-order u in [0, 1].  At reset, the environment
  samples per-channel nonlinear gamma and endpoint offsets, so the same u can
  produce different midrange joint/tendon postures across episodes.
  """

  def __init__(
      self,
      config: config_dict.ConfigDict = hardware_01_randomized_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config=config, config_overrides=config_overrides)


class CubeRotateZAxisHardware01Efficient(CubeRotateZAxis):
  """Milder randomized hardware-01 variant for coordinated, less jittery spins."""

  def __init__(
      self,
      config: config_dict.ConfigDict = hardware_01_efficient_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config=config, config_overrides=config_overrides)


class CubeRotateZAxisHardware01RealCalibrated(CubeRotateZAxis):
  """Hardware-01 variant using the real-tested command window in training."""

  def __init__(
      self,
      config: config_dict.ConfigDict = hardware_01_real_calibrated_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config=config, config_overrides=config_overrides)


class CubeRotateZAxisHardware01RealCalibratedSmooth(CubeRotateZAxis):
  """Real-calibrated variant with hard smoothing for hardware-feasible motion."""

  def __init__(
      self,
      config: config_dict.ConfigDict = hardware_01_real_calibrated_smooth_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config=config, config_overrides=config_overrides)


class CubeRotateZAxisHardware01RealCalibratedAntiTrap(CubeRotateZAxis):
  """Smooth real-calibrated variant that avoids thumb-index trapping."""

  def __init__(
      self,
      config: config_dict.ConfigDict = hardware_01_real_calibrated_anti_trap_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config=config, config_overrides=config_overrides)


class CubeRotateZAxisHardware01RealCalibratedPhysicsID(CubeRotateZAxis):
  """Physics-ID follow-up after real replay showed lateral thumb ejection."""

  def __init__(
      self,
      config: config_dict.ConfigDict = hardware_01_real_calibrated_physics_id_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config, config_overrides)


class CubeRotateZAxisHardware01RealTunedWindow(CubeRotateZAxis):
  """PhysicsID follow-up trained in the operator-tuned real command window."""

  def __init__(
      self,
      config: config_dict.ConfigDict = hardware_01_real_tuned_window_config(),
      config_overrides: Optional[Dict[str, Union[str, int, list[Any]]]] = None,
  ):
    super().__init__(config, config_overrides)


def domain_randomize(
model: mjx.Model, rng: jax.Array):
  mj_model = CubeRotateZAxis().mj_model
  cube_geom_id = mj_model.geom("cube").id
  cube_body_id = mj_model.body("cube").id
  hand_qids = mjx_env.get_qpos_ids(mj_model, consts.JOINT_NAMES)
  hand_body_names = [
      "palm",
      "right_index_f_link",
      "right_index_proximal_link",
      "right_index_middle_link",
      "right_index_distal_link",
      "right_middle_f_link",
      "right_middle_proximal_link",
      "right_middle_middle_link",
      "right_middle_distal_link",
      "right_ring_f_link",
      "right_ring_proximal_link",
      "right_ring_middle_link",
      "right_ring_distal_link",
      "right_pinky_f_link",
      "right_pinky_proximal_link",
      "right_pinky_middle_link",
      "right_pinky_distal_link",
      "right_t_link",
      "right_thumb_mcp_link",
      "right_thumb_proximal_link",
      "right_thumb_distal_link",
  ]
  hand_body_ids = np.array([mj_model.body(n).id for n in hand_body_names])
  fingertip_geoms = ["if_tip", "mf_tip", "rf_tip", "pf_tip", "th_tip"]
  fingertip_geom_ids = [mj_model.geom(g).id for g in fingertip_geoms]

  @jax.vmap
  def rand(rng):
    # Cube friction: =U(0.1, 0.5).
    rng, key = jax.random.split(rng)
    cube_friction = jax.random.uniform(key, (1,), minval=0.1, maxval=0.5)
    geom_friction = model.geom_friction.at[
        cube_geom_id : cube_geom_id + 1, 0
    ].set(cube_friction)

    # Fingertip friction: =U(0.5, 1.0).
    fingertip_friction = jax.random.uniform(key, (1,), minval=0.5, maxval=1.0)
    geom_friction = model.geom_friction.at[fingertip_geom_ids, 0].set(
        fingertip_friction
    )

    # Scale cube mass: *U(0.8, 1.2).
    rng, key1, key2 = jax.random.split(rng, 3)
    dmass = jax.random.uniform(key1, minval=0.8, maxval=1.2)
    cube_mass = model.body_mass[cube_body_id]
    body_mass = model.body_mass.at[cube_body_id].set(cube_mass * dmass)
    body_inertia = model.body_inertia.at[cube_body_id].set(
        model.body_inertia[cube_body_id] * dmass
    )
    dpos = jax.random.uniform(key2, (3,), minval=-5e-3, maxval=5e-3)
    body_ipos = model.body_ipos.at[cube_body_id].set(
        model.body_ipos[cube_body_id] + dpos
    )

    # Jitter qpos0: +U(-0.05, 0.05).
    rng, key = jax.random.split(rng)
    qpos0 = model.qpos0
    qpos0 = qpos0.at[hand_qids].set(
        qpos0[hand_qids]
        + jax.random.uniform(key, shape=(16,), minval=-0.05, maxval=0.05)
    )

    # Scale static friction: *U(0.9, 1.1).
    rng, key = jax.random.split(rng)
    frictionloss = model.dof_frictionloss[hand_qids] * jax.random.uniform(
        key, shape=(16,), minval=0.5, maxval=2.0
    )
    dof_frictionloss = model.dof_frictionloss.at[hand_qids].set(frictionloss)

    # Scale armature: *U(1.0, 1.05).
    rng, key = jax.random.split(rng)
    armature = model.dof_armature[hand_qids] * jax.random.uniform(
        key, shape=(16,), minval=1.0, maxval=1.05
    )
    dof_armature = model.dof_armature.at[hand_qids].set(armature)

    # Scale all link masses: *U(0.9, 1.1).
    rng, key = jax.random.split(rng)
    dmass = jax.random.uniform(
        key, shape=(len(hand_body_ids),), minval=0.9, maxval=1.1
    )
    body_mass = model.body_mass.at[hand_body_ids].set(
        model.body_mass[hand_body_ids] * dmass
    )

    # Joint stiffness: *U(0.8, 1.2).
    rng, key = jax.random.split(rng)
    kp = model.actuator_gainprm[:, 0] * jax.random.uniform(
        key, (model.nu,), minval=0.8, maxval=1.2
    )
    actuator_gainprm = model.actuator_gainprm.at[:, 0].set(kp)
    actuator_biasprm = model.actuator_biasprm.at[:, 1].set(-kp)

    # Joint damping: *U(0.8, 1.2).
    rng, key = jax.random.split(rng)
    kd = model.dof_damping[hand_qids] * jax.random.uniform(
        key, (16,), minval=0.8, maxval=1.2
    )
    dof_damping = model.dof_damping.at[hand_qids].set(kd)

    return (
        geom_friction,
        body_mass,
        body_inertia,
        body_ipos,
        qpos0,
        dof_frictionloss,
        dof_armature,
        dof_damping,
        actuator_gainprm,
        actuator_biasprm,
    )

  (
      geom_friction,
      body_mass,
      body_inertia,
      body_ipos,
      qpos0,
      dof_frictionloss,
      dof_armature,
      dof_damping,
      actuator_gainprm,
      actuator_biasprm,
  ) = rand(rng)

  in_axes = jax.tree_util.tree_map(lambda x: None, model)
  in_axes = in_axes.tree_replace({
      "geom_friction": 0,
      "body_mass": 0,
      "body_inertia": 0,
      "body_ipos": 0,
      "qpos0": 0,
      "dof_frictionloss": 0,
      "dof_armature": 0,
      "dof_damping": 0,
      "actuator_gainprm": 0,
      "actuator_biasprm": 0,
  })

  model = model.tree_replace({
      "geom_friction": geom_friction,
      "body_mass": body_mass,
      "body_inertia": body_inertia,
      "body_ipos": body_ipos,
      "qpos0": qpos0,
      "dof_frictionloss": dof_frictionloss,
      "dof_armature": dof_armature,
      "dof_damping": dof_damping,
      "actuator_gainprm": actuator_gainprm,
      "actuator_biasprm": actuator_biasprm,
  })

  return model, in_axes
