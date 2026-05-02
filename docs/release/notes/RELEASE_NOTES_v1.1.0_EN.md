# rwrsb v1.1.0 Release Notes

> [中文版](RELEASE_NOTES_v1.1.0.md)

## Highlights

- **Blender-style selection gizmo**: introduced in both `rwrsb_anim` and `rwrsb_bind`. After selecting a particle, the viewport shows a 3-axis arrow + ring + center handle widget. Click handles for axis-locked translate / rotate — more intuitive than modifier keys, but the Shift/Ctrl/Alt path remains as a shortcut.
- **Oriented voxel rendering**: in animation mode each voxel cube's orientation rotates with its bone, eliminating the "staircase" silhouette on limb edges at non-90° rotations. GPU data flows through a per-bone `mat4` uniform — even 100k voxels only need 8 KB per frame.
- **Body bridge skinning fix**: hip (`righthip<->lefthip`) and shoulder (`rightshoulder<->leftshoulder`) bridge sticks use midspine as a roll reference, ending the unpredictable twisty drift on the hip / shoulder cluster when the torso bends or rotates.
- **`rwrsb_bind` defaults to voxel box-select on launch** (was the brush tool), avoiding accidental painting.

Non-breaking upgrade: the XML format is fully compatible with v1.0.0 — no breaking changes, hence 1.1.0 rather than 2.0.0.

---

## Changes in This Release

### New Features (gizmo / rendering / UI)

- Selection gizmo (both tools): screen-space constant scale, hover highlight, hit consumes the click; arrows / center → translate, rings → rotate (1 px = 1°, hold Ctrl for 15° snap); arrow length is configurable in the toolbar settings popup (40–200 px).
- Oriented voxel rendering: renderer adds a per-bone orientation `uniform mat4[128]` plus a per-voxel bone-idx VBO; the shader applies `mat3 R = mat3(u_bone_orientations[int(i_bone_idx)])`.
- Body bridge skinning: `_compute_body_bridge_frame` builds an orthonormal basis from the bridge endpoints + midspine, self-consistent between bind and now; recognition is narrow (hip / shoulder pairs only).
- `rwrsb_anim` removes the toolbar Move / Rotate toggle — the gizmo takes over the translate vs rotate distinction.
- `rwrsb_bind` adds a toolbar `View...` popup (world origin axes toggle + gizmo arrow length slider).
- `rwrsb_bind` viewport shows the world origin RGB axes indicator (matching the animation tool).
- `rwrsb_bind` gains a rotate drag path (previously translate-only).

### Behavior Changes

- `EditorState.tool_mode` default value: `"brush"` → `"voxel_select"`.
- `rwrsb_anim` direct particle drag is unconditionally a translation; rotation must be triggered through a gizmo ring.
- Length-Clamp is no longer gated by `anim_drag_mode`; once enabled it applies to every translate (gizmo arrow + direct particle drag).

### Bug Fixes

- Live skinning during drag: voxels follow the skeleton in real time during a particle drag, no more "have to play to see the result".
- After delete / duplicate frame, the viewport pose stays at the `playback_time` interpolation instead of snapping to a keyframe.
- Skinning bind pose rotation tracking fix — eliminates voxel jitter at stick-frame discontinuities.
- Selection gizmo size is stable in side views (previously the world-X-axis-parallel-to-view case caused the scale to blow up).

### Internationalization

- Full English UI translation (added incrementally after v1.0); kept in sync with Chinese via `tr(ui_state, key)`.
- English doc set (README_EN / ARCHITECTURE_EN / RELEASE_EN / CONTRIBUTING_EN / RELEASE_NOTES_*_EN).

### Documentation

- ARCHITECTURE adds Section 10 "Selection Gizmo and Oriented Voxel Rendering"; Section 7 adds the "Body bridge sticks" subsection; field tables and tool_mode default kept in sync.
- README feature overview adds gizmo / world origin / default voxel box-select; the animation tool section gains skinning / voxel orientation notes.

---

## Actions Required from the Project Owner Before Release

- [ ] Run `python main.py`, screenshot the main window (showing the gizmo), update `docs/screenshot.png`.
- [ ] Run `build.bat`, confirm output at `dist\rwrsb_bind\rwrsb_bind.exe`.
- [ ] Launch both exes, confirm they run; select a particle and verify gizmo rendering, arrow drag, ring drag.
- [ ] Load a vanilla animation and play it — visually confirm limbs are smooth at non-90° rotations (no staircase); hip / shoulder clusters no longer twist when the torso bends.
- [ ] Tag `v1.1.0`, zip as `rwrsb_bind-v1.1.0-windows.zip`, upload to GitHub Release.

---

## Known Limitations

- The bind tool's rotate pivot is currently fixed to the active particle; it does not yet have an active / centroid / world_origin selector like the animation tool. Can be added later if requested.
- Gizmo rotation direction is currently "1 px = 1°, rightward is positive". Around different axes the direction may feel counterintuitive. Not adjusted in this release — pending real-world feedback.
- Oriented voxel rendering performance has not been measured on million-voxel models. The architecture should support it (per-frame upload remains ~8 KB), but it has not been stress-tested.
