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
| `_particle_positions_before_anim` | Particle position backup taken before entering animation mode; restored by `exit_animation_mode` |
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
| `"bone_edit"` | Bone editing | Click a particle to select it; supports multi-select/box-select; **particle dragging only works in this mode** |

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

---

## 6. Binding Mode vs Animation Mode State Transitions

### Entering animation mode: `enter_animation_mode(animation)`

Precondition: `len(particles) == EXPECTED_PARTICLE_COUNT (15)`, otherwise raises `ValueError`.

Execution order:
1. If `animation.frames` is empty, automatically append one frame (= current particle pose)
2. Back up current particle positions to `_particle_positions_before_anim`
3. Clear `selected_particles` and mirror mode
4. Set `animation_mode = True`, clear animation undo/redo stacks
5. Call `record_voxel_bind_pose()` with the still pose (the backed-up positions) as the bind pose
6. Call `_apply_frame_to_particles(0)` to set particle positions to frame 0
7. Call `_record_reference_lengths()` to record per-stick reference lengths

### Exiting animation mode: `exit_animation_mode(force=False)`

- If `_anim_dirty == True` and `force=False`, returns `"dirty_needs_confirmation"` — the UI layer shows a confirmation dialog.
- Otherwise: restores particle positions from `_particle_positions_before_anim` and calls `update_voxel_positions_from_skeleton()` to return voxels to the bind pose.

### Key distinction: skinning is only triggered in animation mode

`_mark_skeleton_changed()` calls `update_voxel_positions_from_skeleton()` (skinning) only when `animation_mode == True`. It does not call it in binding mode.

Reason: In binding mode, voxels are the actual geometry — dragging a particle only moves the skeleton annotation point; voxel positions should not follow. In animation mode, voxels must deform with the skeleton (skinning effect).

---

## 7. Key Conventions and Implicit Knowledge

### EXPECTED_PARTICLE_COUNT = 15

Defined in `animation_io.py`. The RWR engine hard-codes this: a soldier animation XML must have exactly 15 particle positions per frame — one more or one less will cause a parse failure. Skeleton loading, frame editing, and XML export in the animation tool all depend on this constraint.

### constraintIndex == sticks list index

`StickEntry.constraint_index` must always equal the stick's array index in `EditorState.sticks`. This invariant is maintained by `_normalize_stick_indices()`, which is called after every stick add, delete, or reorder. Since the binding keys are also constraint indices, `_normalize_stick_indices()` is also responsible for remapping the bindings.

### trans_bias: 127 vs 49

`trans_bias` is the coordinate offset from MagicaVoxel space to RWR world space, derived from the RWR engine coordinate system definition (see `Transformation` in `rwrwc.py`).

- Default `127`: for humanoid soldier models
- `49`: for weapon models (smaller bounding volume, smaller bias)

Changing `trans_bias` shifts all voxel and skeleton coordinates together, so their relative relationship stays the same.

### Presets store only the skeleton, not bindings

Skeleton presets (`presets/*.json`) store only `particles` + `sticks`, not `bindings`. Bindings are project-specific data tied to a particular voxel model and have no cross-model reuse value. Loading a preset clears the bindings.

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
