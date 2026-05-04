# rwrsb v1.1.2 Release Notes

> [中文](RELEASE_NOTES_v1.1.2.md)

This is a maintenance release after v1.1.1. The focus is wiring the `rwrsb_bind` skeleton-authoring workflow into viewport operations (pick particles / sticks, extend chains, bulk move, delete, undo restoring selection), plus fixing a particle-panel tree-node bug that overwrote selection state every frame.

## Highlights

- **Author skeletons directly in the viewport**: selecting particles, connecting sticks, spawning new particles, and extending chains can all be done in the viewport without bouncing through the side panel.
- **Particle-panel tree node no longer overrides external active**: previously an expanded tree node would force `active_particle_idx` back to its idx every frame, so clicking blank wouldn't deselect, the side panel flickered, and the gizmo got locked at the world origin. Now active is only set on the frame the header is clicked.
- **Undo / redo restores the selection set**: undo snapshots include `selected_particles`, so selection survives undo / redo.

## Changes

### Bind viewport workflow (`rwrsb_bind`)

- Click a stick in the viewport to set it active; a plain stick click clears the particle selection so a follow-up chain doesn't start from the wrong particle.
- Repeated clicks on overlapping particles cycle through the hit candidates.
- Particle picking takes priority over the gizmo so the active particle's 80-px arrows don't swallow clicks on other particles.
- One-click `connect` builds a stick between two selected particles.
- Spawn a new particle near the active particle along X / Y / Z (spawn-near).
- Extend-chain workflow: spawn a new particle along an axis from the active particle and auto-link a stick; the new particle becomes active for chained extensions.
- `Delete` key / button removes the selected particles or the active stick; bulk deletion is a single undo step.
- Arrow keys nudge all `selected_particles`; the entire nudge is one undo step.
- In mirror mode, particle drag grid-snapping also quantizes the mirror normal direction.
- Box-select stale-modifier bug fixed: modifiers at the start of each new box decide the semantics.

### Particle panel

- Filter list by name / ID; the active particle's tree node auto-expands so the panel follows selection changes.
- **Fix**: tree node no longer calls `set_active_particle` unconditionally each frame; it now only sets active on the frame the header is clicked. This fixes the trio of symptoms: "blank click doesn't deselect, side panel flickers, gizmo locked at world origin".

### Rendering / highlighting

- The bind tool now syncs `renderer.highlight_active_particle_idx`, distinguishing the active particle (cyan) from other selected particles (light yellow) in multi-select.

### Data / persistence

- `save_xml` always uses the live `self.sticks` instead of the load-time snapshot.
- Undo snapshots include `selected_particles`, so the selection set is fully restored on undo / redo.

## Known Limitations

- Same as v1.1.1: gizmo rotation still rotates selected particle coordinates rather than acting as a persistent object-level transform.
- Non-90° whole-model rotation still suffers resampling / distortion when written directly into voxel coordinates because XML voxel coordinates are integerized.
