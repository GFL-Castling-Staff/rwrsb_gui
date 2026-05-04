# rwrsb Architecture Overview

> [中文版](ARCHITECTURE.md)

This document is aimed at "the project owner returning after six months" and "a technical contributor joining for the first time". The goal is to give the reader a sufficient mental model within 20 minutes before diving into the actual code.

---

## 1. Two Entry Points

The repository has two independent executable entry points:

| Entry point | Built binary | Purpose |
|-------------|-------------|---------|
| `main.py` | `rwrsb_bind.exe` | Binding tool: edit the skeleton structure and voxel binding of voxel models |
| `main_animation.py` | `rwrsb_anim.exe` | Animation tool: author keyframe animations for RWR soldier skeletons |

Both entry points **share the same source modules** (`editor_state.py`, `ui_panels.py`, `renderer.py`, `camera.py`, `xml_io.py`, etc.). At startup each creates its own `EditorState` and `UIState` instances (stored in module-level globals `g_editor` / `g_ui`).

The `UIState.app_mode` field (`"skeleton"` / `"animation"`) is the runtime dispatch key:
- Panel rendering functions in `ui_panels.py` read this field to decide which panels and buttons to show.
- `main.py` sets `g_ui.app_mode = "skeleton"` at startup; `main_animation.py` sets `"animation"`.

The main loop structure is identical in both entry points (GLFW init → frame loop → ImGui render → event dispatch), but the animation tool additionally handles playback ticks (`playback_time` advancement) and the frame timeline UI.

---

## 2. EditorState — The Central State Object

`EditorState` (`editor_state.py`) is the de facto singleton state center of the project. Each entry-point process has one `g_editor = EditorState()` instance that holds all editable data and runtime state.

### File data
| Field | Type | Description |
|-------|------|-------------|
| `voxels` | `list` | Voxel list; each element is a dict with position + color |
| `particles` | `list` | Skeleton node list; each element contains `id`, `x/y/z`, `name`, etc. |
| `sticks` | `list[StickEntry]` | Stick (bone segment) list |
| `bindings` | `dict` | `{constraint_index: [voxel_index, ...]}` |
| `source_path` | `str \| None` | Path of the currently open file |
| `trans_bias` | `int` | MagicaVoxel → world coordinate offset; default 127, weapon models use 49 |

### Selection state
| Field | Description |
|-------|-------------|
| `selected_voxels` | `set[int]` — selected voxel index set |
| `selected_particles` | `set[int]` — selected particle index set |
| `active_stick_idx` | Index of the currently active stick (used for panel highlighting) |
| `active_particle_idx` | The "last-clicked" particle index in a multi-selection; `-1` means none |

### Tool mode and mirror mode
| Field | Description |
|-------|-------------|
| `tool_mode` | `"brush"` / `"voxel_select"` / `"bone_edit"` — see Section 4 |
| `mirror_mode` | `bool` — whether mirror editing mode is active |
| `mirror_axis` | `"x"` / `"y"` / `"z"` |
| `mirror_pair` | `tuple[int, int] \| None` — the two particle indices being mirrored |
| `mirror_plane_origin` | `np.ndarray(3,)` — mirror plane origin |
| `mirror_plane_normal` | `np.ndarray(3,)` — mirror plane normal |
| `mirror_edit_mode` | `bool` — mirror plane editing sub-mode |

### Undo / Redo
| Field | Description |
|-------|-------------|
| `_undo_stack` | Snapshot list (cap 64); see `_snapshot` / `_restore_snapshot` |
| `_redo_stack` | Redo snapshot list |
| `_dirty` | Whether XML data has unsaved changes (read by the title bar `*`) |

### Animation mode
| Field | Description |
|-------|-------------|
| `animation_mode` | `bool` — whether animation editing mode is active |
| `current_animation` | `animation_io.Animation \| None` |
| `animation_source_doc` | `AnimationDocIndex \| None` — source document index |
| `animation_source_idx` | Index of the animation within the source document |
| `current_frame_idx` | Index of the currently edited frame |
| `playback_time` | Playback time in seconds |
| `playback_playing` | `bool` — whether playback is running |
| `playback_loop_preview` | `bool` — loop preview toggle (independent of `anim.loop`) |
| `_particle_positions_before_anim` | Particle position backup taken before entering animation mode; used only for `exit_animation_mode` restore |
| `_canonical_skeleton_pose` | Canonical particle coordinates captured after skeleton/model load; preferred source for animation skinning bind pose |
| `_canonical_voxel_positions` | Canonical voxel list captured after skeleton/model load; restored before recording animation bind-pose local offsets |
| `_anim_dirty` | Whether animation data has unsaved changes |
| `_anim_undo_stack` | Animation-mode-specific undo stack |
| `_anim_redo_stack` | Animation-mode-specific redo stack |
| `_anim_reference_lengths` | Per-stick reference lengths recorded on entering animation mode (used by the stick length check) |

### Baseline pose
| Field | Description |
|-------|-------------|
| `_baseline_positions` | `list[tuple] \| None` — particle positions for the baseline pose |
| `_baseline_name` | Baseline pose name (e.g., `"vanilla_still"`) |
| `_baseline_locked_indices` | `set[int]` — particle indices locked (undraggable) in baseline mode |

### Skeleton tree cache
| Field | Description |
|-------|-------------|
| `_tree_parent` | `dict[int, int \| None]` — particle index → parent index; root's parent is `None` |
| `_tree_root_idx` | Particle index of the current root; `-1` means not built |
| `_tree_dirty` | When `True`, the tree must be rebuilt before next access |

### Render sync and skinning
| Field | Description |
|-------|-------------|
| `gpu_dirty` | GPU render buffer needs to be rebuilt |
| `skeleton_dirty` | Skeleton line data needs to be re-uploaded to the renderer |
| `_voxel_local_offsets` | `{voxel_index: np.ndarray(3,)}` — fixed local-space offset of each bound voxel within its stick's coordinate frame (skinning bind pose) |
| `_voxel_groups` | Skinning data pre-grouped by `constraint_index`; used by `update_voxel_positions_from_skeleton` |
| `_bone_orientations` | `np.ndarray(MAX_BONE_SLOTS, 16)` — per-bone R_cube matrix (mat4 column-major), used for oriented voxel rendering. Slot 0 is the identity sentinel |
| `_voxel_bone_indices` | `np.ndarray(N_voxels,)` — per-voxel bone slot index (bound voxel = ci+1, unbound = 0); used by the shader as a uniform array index |

---

## 3. Relationships Between the Three Core Data Sets

```
particles ──── sticks ──── bindings
   │              │             │
 id (uint)  constraint_index  key = constraint_index
 index       == sticks index   value = [voxel_index, ...]
```

**particles**: Skeleton nodes. Each has a unique `id` (persisted to XML) and an array `index` (used by UI state). These are distinct — adding or deleting a particle changes `index` values but not `id` values.

**sticks**: Bone segments. Each `StickEntry` references two particles by their `id` (`particle_a_id` / `particle_b_id`). `StickEntry.constraint_index` must always equal the stick's position in the `self.sticks` list — `_normalize_stick_indices()` enforces this invariant after every add/delete.

**bindings**: `{constraint_index: [voxel_index, ...]}` — records which voxels are bound to which stick. After deleting or reordering sticks, the binding keys (constraint indices) are remapped together by `_normalize_stick_indices()`, otherwise "voxel bound to wrong stick" silent errors will occur.

Key constraint: **deleting or reordering a stick must always update bindings in sync** — this is the most bug-prone operation in the project; validate carefully.

---

## 4. tool_mode Three-State Semantics and Transition Side-Effects

`EditorState.tool_mode` controls mouse behavior in the viewport. The three values are mutually exclusive:

| Value | Semantics | Left-click behavior |
|-------|-----------|---------------------|
| `"brush"` | Voxel painting | Click a voxel to bind/paint it |
| `"voxel_select"` | Voxel box-select | Drag to draw a box; updates `selected_voxels` |
| `"bone_edit"` | Bone editing | Click a particle to select it; supports multi-select/box-select; **particle dragging and the selection gizmo only work in this mode** |

**Default value (since v1.1.0): `"voxel_select"`**. Newly opened models start in an observation-friendly mode to avoid accidental painting.

> Note: `tool_mode` (what the mouse does in the viewport) and `allow_skeleton_edit` / `allow_stick_edit` / `allow_particle_edit` (whether data modification is permitted) are two orthogonal concepts — do not confuse them.

**Transition side-effects** (executed by `set_tool_mode()`):
- Leaving `"bone_edit"`: `selected_particles.clear()`, `active_particle_idx = -1`, calls `exit_mirror_mode()`
- Leaving `"voxel_select"`: `selected_voxels` is **preserved** (consistent with existing behavior)

Toolbar shortcuts: `B` (brush) / `V` (voxel_select) / `E` (bone_edit).

---

## 5. Modifier Key Semantics Reference

The same modifier key has different meanings in different contexts:

| Context | Shift | Ctrl | Alt | Shift+Alt |
|---------|-------|------|-----|-----------|
| Particle drag axis constraint | Lock X | Lock Y | Lock Z | — |
| Click particle multi-select | Add (append) | Toggle (remove if already selected) | — | Remove (deselect) |
| Box-select particles | Add (append) | Toggle | — | Remove (deselect) |

Axis constraints (during drag) and multi-select (during click/box-select) read modifier keys at different times: axis constraints are read at **drag start (mousedown + movement)**; multi-select is read at **click (mousedown + no movement + mouseup)**. Therefore they do not conflict.

**Gizmo precedence**: When mouse-down hits a gizmo handle (arrow / ring / center), the axis is fixed by the handle and **modifier keys are ignored**. See Section 10.

---

## 6. Binding Mode vs Animation Mode State Transitions

### Entering animation mode: `enter_animation_mode(animation)`

Precondition: `len(sticks) == EXPECTED_STICK_COUNT (17)`, otherwise raises `ValueError`.

Execution order:
1. If `animation.frames` is empty, automatically append one frame (= current particle pose)
2. If no exit-restore backup exists yet, back up current particle positions to `_particle_positions_before_anim`
3. Clear `selected_particles` and mirror mode
4. Set `animation_mode = True`, clear animation undo/redo stacks
5. Choose the bind-pose source: prefer `_canonical_skeleton_pose`, fallback to `_particle_positions_before_anim` only if canonical data is unavailable
6. If `_canonical_voxel_positions` exists and matches the current voxel count, restore `self.voxels` to canonical positions first so the previous animation's skinned voxel positions cannot contaminate local offsets
7. Call `record_voxel_bind_pose()` with that bind pose
8. Call `_apply_frame_to_particles(0)` to set particle positions to frame 0
9. Call `_record_reference_lengths()` to record per-stick reference lengths

### Exiting animation mode: `exit_animation_mode(force=False)`

- If `_anim_dirty == True` and `force=False`, returns `"dirty_needs_confirmation"` — the UI layer shows a confirmation dialog.
- Otherwise: restores particle positions from `_particle_positions_before_anim` and calls `update_voxel_positions_from_skeleton()` to return voxels to the bind pose.

### Key distinction: skinning is only triggered in animation mode

`_mark_skeleton_changed()` calls `update_voxel_positions_from_skeleton()` (skinning) only when `animation_mode == True`. It does not call it in binding mode.

Reason: In binding mode, voxels are the actual geometry — dragging a particle only moves the skeleton annotation point; voxel positions should not follow. In animation mode, voxels must deform with the skeleton (skinning effect).

---

## 7. Key Conventions and Implicit Knowledge

### EXPECTED_STICK_COUNT = 17

Defined in `animation_io.py`. The RWR engine constraint for soldier animation is **exactly 17 sticks per frame**, NOT particle count. The engine does not enforce any particle count limit (15 particles is a vanilla humanoid skeleton convention, not a hard engine restriction). It also does not enforce connectivity or topology — isolated, unbound sticks load fine.

Skeleton loading, frame editing, and XML export in the animation tool all depend on this constraint. A pre-flight dialog checks stick count before entering animation mode and guides the user to pad or prune as needed.

### constraintIndex == sticks list index

`StickEntry.constraint_index` must always equal the stick's array index in `EditorState.sticks`. This invariant is maintained by `_normalize_stick_indices()`, which is called after every stick add, delete, or reorder. Since the binding keys are also constraint indices, `_normalize_stick_indices()` is also responsible for remapping the bindings.

### trans_bias: 127 vs 49

`trans_bias` is the coordinate offset from MagicaVoxel space to RWR world space, derived from the RWR engine coordinate system definition (see `Transformation` in `rwrwc.py`).

- Default `127`: for humanoid soldier models
- `49`: for weapon models (smaller bounding volume, smaller bias)

Changing `trans_bias` shifts all voxel and skeleton coordinates together, so their relative relationship stays the same.

### Presets store only the skeleton, not bindings

Skeleton presets (`presets/*.json`) store only `particles` + `sticks`, not `bindings`. Bindings are project-specific data tied to a particular voxel model and have no cross-model reuse value. Loading a preset clears the bindings.

### Heterogeneous skeletons and dummy sticks

The RWR engine only enforces stick count = 17; topology is unrestricted. This enables **heterogeneous skeletons** (non-humanoid, e.g. quadrupeds, mechanical rigs). Key mechanisms:

- **dummy stick**: A stick with no voxel binding and topologically isolated (neither endpoint shared with another stick). Used to pad the count to 17, satisfying the engine constraint.
- **`classify_sticks()`** (`editor_state.py`): Classifies each stick as `skinned` (has binding), `connected_unskinned` (has topology but no binding), or `dummy` (isolated, no binding).
- **One-click pad** (`pad_dummy_sticks_to_target()`): Auto-creates `_dummy_N_a/b` particles and matching dummy sticks far from the model to reach 17. Undo-supported.
- **Pre-flight check**: A dialog appears before entering animation mode if stick count != 17, showing the delta and guiding the user (< 17: one-click pad, > 17: manual prune).
- **Visual distinction**: Dummy sticks render in gray with reduced alpha in the 3D viewport; the bone panel has an independent dummy visibility toggle; the panel list marks dummies with `[D]` prefix and connected_unskinned sticks with `(unbound)`.

### Table-driven lateral-reference skinning

Two-endpoint sticks do not have a third vector to define roll around their main axis. The generic "shortest bind→now rotation" algorithm (`_rotate_basis`) can leave unpredictable twist when such sticks become nearly vertical or change pose significantly.

Skinning now consults `_LATERAL_REF_RULES_BY_ID` / `_LATERAL_REF_RULES_BY_NAME` to decide whether a stick should build an orthonormal basis with a lateral reference. Id rules match first; name rules are the fallback for presets with non-vanilla ids. Rule types:

- `"midspine_to_origin"`: used by hip / shoulder bridges. The reference vector is midspine relative to the bridge center.
- `"shoulder_lateral"`: used by neck→head, elbow→hand, midspine/shoulder, and shoulder/neck upper-body sticks. The reference vector is the left-right shoulder line.
- `"hip_lateral"`: used by hip→midspine and leg sticks. The reference vector is the left-right hip line.

The unified entry point is `_compute_body_bridge_frame()`: it looks up the lateral reference type, then calls `_basis_from_axis_and_reference()` to build the basis. Bind-time and now-time use the same rules, keeping the local↔world mapping self-consistent. If required reference particles are missing or a vector degenerates, it returns `None` and the caller falls back to the `_rotate_basis` shortest-rotation path.

### stick.visible is not cloned — it goes through the visible_by_pair channel

`StickEntry.clone()` does not copy the `visible` field (counterintuitive!). Reason: `visible` is UI state (the user's display preference) and should not be reset by undo/redo. `_snapshot()` separately saves visibility state in a `visible_by_pair` dict (key = `(particle_a_id, particle_b_id)`); `_restore_snapshot()` matches it back by particle pair on restore — unmatched sticks default to `True`. See Section 8.

---

## 8. Five Dirty Flags Reference

| Flag | Meaning | Set by | Consumed / cleared by |
|------|---------|--------|-----------------------|
| `_dirty` | XML data has unsaved changes | Any skeleton / binding modification (`_mark_skeleton_changed` / `_mark_bindings_changed`) | Cleared after file save; read by title bar `*` and exit guard |
| `gpu_dirty` | GPU render buffer needs rebuilding | Same as above, plus voxel visibility changes | Render loop checks each frame; cleared after buffer rebuild |
| `skeleton_dirty` | Skeleton line data needs re-upload to renderer | `_mark_skeleton_changed()` | Cleared after renderer re-uploads skeleton lines |
| `_tree_dirty` | Skeleton tree cache is stale | Particle / stick add/delete/modify (`_mark_skeleton_changed`) | Cleared after `_rebuild_tree()` runs before next `_tree_parent` access |
| `_anim_dirty` | Current animation has unsaved changes | Frame editing operations in animation mode | Cleared after animation save; read by animation panel title `*` and exit guard |

`gpu_dirty` and `skeleton_dirty` are often set at the same time but consumed by different systems: `gpu_dirty` triggers VBO rebuild (voxel colors); `skeleton_dirty` triggers skeleton line data re-upload (each has its own GPU buffer).

---

## 9. bone / stick Naming and particle id / index Distinction

### bone vs stick

`bone` is the early project naming; it was later unified to `stick`. Both naming conventions currently coexist in the codebase:

- **Current naming** (primary): `StickEntry`, `self.sticks`, `active_stick_idx`, `set_all_sticks_visible()`
- **Legacy aliases** (compatibility): `@property bones` (forwards to `sticks`), `@property active_bone_idx` (forwards to `active_stick_idx`), constant `BONE_COLORS`

Legacy aliases are kept for forward compatibility (historical handoff documents and early code reference them). **New code should use the `stick` series exclusively** — do not use the `bone` aliases.

### particle id vs index

A particle has two kinds of "number" with different semantics and uses:

| | `id` | `index` |
|-|------|---------|
| Type | `int` (uint), stored in the particle dict's `"id"` field | Array index (0-based) |
| Used for | XML persistence; `StickEntry.particle_a_id / particle_b_id` | UI selection state: `selected_particles`, `active_particle_idx` |
| Stability | Does not change when particles are added or deleted | May change for other particles when a particle is added or deleted |

Rule: **use `id` for anything that must be persisted to file or kept stable across undo frames; use `index` for UI state that is only valid within the current session.**

---

## 10. Selection Gizmo and Oriented Voxel Rendering (v1.1.0)

### 10.1 Selection gizmo

A Blender-style 3-axis widget available in both tools. The gizmo center and rotation pivot are the same point, computed from `UIState.rotate_pivot_mode`:

- `"active"`: active particle; if active is not in the selection, fallback to centroid
- `"centroid"`: geometric center of current `selected_particles`
- `"world_origin"`: world origin `(0, 0, 0)`

**Visibility conditions**:
- Animation tool: `active_particle_idx` is valid + not in mirror mode
- Binding tool: above + `tool_mode == 'bone_edit'` + `allow_particle_edit` is `True`

The gizmo is hidden if any condition fails.

**Geometry**:
- Three line arrows (X red / Y green / Z blue), each with an X-shaped head at the tip
- Three 32-segment polyline rings (matching colors, in the plane perpendicular to the corresponding axis)
- A small 3-axis cross at the center
- Depth test off — drawn on top; the hovered handle turns yellow

**Screen-space constant scale**: each frame, project three world unit vectors (X/Y/Z) and take the maximum screen-space distance as `pixels_per_world`. **Do not use a single vector**: in side views the chosen world axis can be parallel to the view direction, collapsing the projected distance to ~0 and blowing the arrow length to infinity (this was a real bug fixed mid-v1.1.0). `arrow_world_length = arrow_pixels / pixels_per_world`. `arrow_pixels` defaults to 80, adjustable in the toolbar settings popup (40–200).

**Hit test** (screen-space 2D distance):
- Center: distance to `pivot_2d` < 8 px
- Arrow: distance to the projected line segment < 10 px
- Ring: minimum distance from any of 24 sampled points on the ring < 10 px
- Priority: center > arrow > ring (ties broken by priority)

**Interaction routing**:
- Hit arrow / center → start `_begin_particle_drag` / `_start_particle_drag` with an `axis_preset` that overrides modifier keys
- Hit ring → start a rotate drag around the pivot computed from `rotate_pivot_mode` and the preset world axis; 1 px = 1°, hold Ctrl for 15° snap
- Direct particle drag (no gizmo hit): legacy path unchanged; modifier keys Shift/Ctrl/Alt still lock X/Y/Z

The binding tool had no rotate drag before v1.1.0; it was ported from the animation tool (does not call `commit_particle_move_to_frame` / `apply_baseline_lock` / live skinning, uses `_push_undo` instead of `_anim_push_undo`).

### 10.2 Oriented voxel rendering

When the skeleton rotates, each voxel cube's **own orientation** must rotate with it; otherwise non-90° rotations produce a "staircase" silhouette on limb edges.

**Data layout** (per-bone uniform, **not** per-voxel attribute):
- `_bone_orientations`: shape `(128, 16)` — each row is a column-major-flattened mat4
- Slot 0: identity sentinel — unbound voxels' `i_bone_idx` points here
- Slot ci+1: `R_cube = R_now @ R_bind.T` for stick `ci` (R_bind is recorded by `record_voxel_bind_pose`; body bridge sticks go through the body bridge path with the same self-consistent construction)
- `_voxel_bone_indices`: shape `(N_voxels,)` float32 — bound voxel = `ci+1`, unbound = 0

**Why per-bone, not per-voxel**: for a 100k-voxel model, a per-voxel orientation VBO would re-upload 3.6 MB per frame. The per-bone uniform only needs 8 KB (128 mat4) per frame, independent of voxel count.

**Shader ([shaders/voxel.vert](shaders/voxel.vert))**:
```glsl
uniform mat4 u_bone_orientations[128];
in float i_bone_idx;
...
mat3 R = mat3(u_bone_orientations[int(i_bone_idx)]);
vec3 world_pos = R * in_vert + i_pos;
v_normal = R * in_normal;   // R is orthonormal; no inverse-transpose needed
```

**Trigger**: animation mode only. `update_voxel_positions_from_skeleton` computes `R_cube` per stick and writes it into `_bone_orientations[ci+1]`. In binding mode all slots stay identity, voxel cubes remain axis-aligned, preserving historical behavior.

**Bone idx VBO upload timing**: only when bindings change (rebuilt inside `build_instance_arrays`). Each animation tick only uploads the orientations uniform.
