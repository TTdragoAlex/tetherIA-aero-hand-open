# 45 mm Ball Visual-Fix Rollouts

These videos were regenerated on 2026-07-10 from the completed ball policy
checkpoint `000157286400`.

The original training XML already used a `0.0225 m` radius sphere, which is a
45 mm diameter ball. However, the first copied rollout videos were visually
misleading because the main physical sphere was in render/collision group `3`,
while only a small black orientation marker was in visible group `2`.

This visual-fix render keeps the same physical collision sphere and adds a
non-colliding visible orange sphere:

- Physical sphere: `size="0.0225"`, mass `0.055`, group `3`.
- Visual sphere: `size="0.0225"`, no contact, no density, group `2`.
- Orientation marker: black surface dot, no contact, group `2`.

Use these `rollout*.mp4` files for visual review of the 45 mm ball run.
