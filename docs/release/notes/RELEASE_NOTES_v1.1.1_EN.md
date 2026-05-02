# rwrsb v1.1.1 Release Notes

> [中文](RELEASE_NOTES_v1.1.1.md)

This is a maintenance release after v1.1.0. It focuses on gizmo pivot consistency, skinning contamination after animation switches, and roll drift on more stick types during large pose changes.

## Highlights

- **Unified pivot selector in both tools**: gizmo ring rotation in `rwrsb_bind` and `rwrsb_anim` now follows the same pivot selector: active particle, selection centroid, or world origin.
- **Canonical bind-pose fix**: animation mode records skinning local offsets from the canonical pose captured when the skeleton/model was loaded, and restores canonical voxel positions first so one animation's skinned voxels cannot contaminate the next animation.
- **Table-driven lateral-reference skinning**: the original hip/shoulder bridge special case is now a rule table covering neck/head, hand endpoints, chest/shoulder cross sticks, and leg sticks, reducing roll drift on two-point sticks.

## Changes

### Gizmo / UI

- `UIState.rotate_pivot_mode` now drives both the gizmo center and ring-rotation pivot in both tools.
- Pivot modes:
  - `active`: active particle; falls back to selection centroid if active is not in the selection.
  - `centroid`: geometric center of selected particles.
  - `world_origin`: world origin.
- `rwrsb_bind` no longer has a fixed active-particle rotate pivot.

### Skinning

- Added `_canonical_skeleton_pose` and `_canonical_voxel_positions`, captured after skeleton/model load as canonical bind state.
- `enter_animation_mode()` prefers canonical skeleton pose when recording bind pose.
- Before recording voxel local offsets, `self.voxels` is restored to canonical voxel positions so live skinning from a previous animation cannot pollute the next animation.
- Lateral-reference rules are now table-driven:
  - `"midspine_to_origin"`: hip / shoulder bridges.
  - `"shoulder_lateral"`: neck→head, elbow→hand, midspine/shoulder, shoulder/neck upper-body sticks.
  - `"hip_lateral"`: hip→midspine and leg sticks.

### Documentation

- README now documents gizmo pivot modes, canonical bind pose, and lateral-reference skinning.
- ARCHITECTURE now documents the updated animation-mode entry flow, canonical state fields, table-driven lateral-reference rules, and gizmo pivot semantics.
- Outdated Claude implementation prompt / handoff documents were moved to local `history/archive/` and excluded with `.gitignore`; they are no longer release documentation.

## Known Limitations

- Gizmo rotation still rotates selected particle coordinates. It is not a persistent object-level transform. Blender-style object-mode rotation of voxel + skeleton together should be designed as a separate feature.
- Non-90° whole-model rotation still has a persistence problem if written directly into voxel coordinates, because XML voxel coordinates are integerized and can cause resampling/distortion.
