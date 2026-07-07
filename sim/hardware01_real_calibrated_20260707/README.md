# Hardware01 Real-Calibrated Rollouts - 2026-07-07

These rollout videos were copied from the Ubuntu training PC after the
`AeroCubeRotateZAxisHardware01RealCalibrated` training run completed.

## Source Run

- Training PC path:
  `/home/hw/aero-hand-sim/logs/AeroCubeRotateZAxisHardware01RealCalibrated-20260707-093704-aero_hardware01_real_calibrated_fresh_20260707_093702`
- Run id: `aero_hardware01_real_calibrated_fresh_20260707_093702`
- Final checkpoint: `000157286400`
- Final logged reward: `35.862`
- Best logged reward observed in the training log: `37.066` at `137625600`

## Files

- `aero_hardware01_real_calibrated_fresh_20260707_093702.log`
- `config.json`
- `rollout0.mp4`
- `rollout1.mp4`
- `rollout2.mp4`

## Notes

Inspect these videos before exporting a real-hand actor or replaying a trace on
hardware. The safety gate is still: sim motion should show plausible
thumb/finger opposition and cube rotation, not only caging or static clamping.
