# RWRSB - rwrsb_bind + rwrsb_anim

> [中文版](README.md)

`rwrsb_bind` is a voxel skeleton binding editor for RWR-style assets.

It loads `.vox` files or project XML directly, lets you edit the skeleton structure and voxel binding relationships, and exports back to the target XML format. The focus of the current version is "practical skeleton editing and reuse", not just re-binding points on the default humanoid skeleton.

![rwrsb_bind screenshot](docs/screenshot.png)

## Feature Overview

- Load MagicaVoxel `.vox` files
- Load project-compatible XML
- Edit `particle` nodes
- Edit `stick` connections
- Re-bind voxels to skeleton segments
- Save and reuse skeleton presets
- Drag particles directly in the viewport
- **Blender-style selection gizmo** (3-axis arrows + rings) — click handles for axis-locked translate / rotate, with Active / Median / World pivot modes
- World origin RGB axes indicator
- Grid display, major/minor grid, and grid snapping
- Chinese / English bilingual UI
- UI scaling
- Camera Y-axis inversion
- Export to XML
- Export to MagicaVoxel `.vox` (voxels only — skeleton and bindings are not included)
- Defaults to voxel box-select on launch (avoids accidental painting)

## Requirements

- Windows
- Python 3.10+
- Working OpenGL drivers

Main dependencies:

- `moderngl`
- `glfw`
- `imgui[glfw]`
- `numpy`

## Quick Start

First-time environment setup:

```bat
setup.bat
```

Launch the editor:

```bat
run.bat
```

Or run directly:

```bat
.venv\Scripts\python main.py
```

To open a file on launch:

```bat
.venv\Scripts\python main.py path\to\model.vox
```

## Animation Editor (rwrsb_anim.exe)

`rwrsb_anim` is the second tool in this repository, used for creating and modifying RWR soldier XML animations.

Launch command:

```bat
.venv\Scripts\python main_animation.py
```

### Startup Behavior

On launch, the tool automatically loads the built-in vanilla humanoid skeleton (15 particles) and enters an empty animation editing mode — you can start keyframing immediately.

### Three Workflows

**A. Create from Scratch**

Drag particles to pose → add frames → adjust frame timing on the timeline → save as XML.

**B. Edit a Vanilla Animation**

Click "Load Animation" in the toolbar → select `soldier_animations.xml` → choose `walking` (or any other animation) → edit frames → save.

**C. Custom Skeleton**

Click "Open Skeleton" in the toolbar → select a custom skeleton XML (must have exactly 15 particles) → create or load an animation → edit → save.

You can also drag an XML file directly onto the window; the tool will automatically detect whether it is a skeleton file or an animation file.

### File Compatibility

- Output XML is compatible with `soldier_animations.xml` and can be read directly by the RWR engine.
- Animation XML exported by `rwrac.exe` can be loaded as input (note that rwrac's particle name fields usually have a `.dae` suffix; the animation data is usable, but any logic that depends on particle names will need to be corrected manually).

### Grid Snapping

The "Grid..." button in the toolbar toggles the viewport grid and particle drag snapping. Supports step sizes of 0.5, 1, or a custom value. The three planes (XZ / XY / YZ) can be toggled independently.

### Stick Length Check

The "Check stick lengths" checkbox in the lower-right of the animation panel enables real-time display of sticks whose length deviates from the frame-0 reference length by more than the configured threshold, highlighted in red in the viewport. The default threshold is 1% (matching the natural drift in vanilla animations).

### Selection Gizmo / Skinning / Voxel Orientation

- Selecting a particle shows a Blender-style 3-axis gizmo in the viewport: drag arrows to translate along an axis, drag rings to rotate around an axis (Ctrl for 15° snap), drag the center handle to translate freely. Ring rotation in both tools follows the toolbar pivot selector: active particle, selection centroid, or world origin. The Shift / Ctrl / Alt modifier-key axis lock still works as a shortcut when dragging particles directly.
- Skinning: sticks that are prone to roll drift use table-driven lateral reference rules. Hip/shoulder bridges use midspine; neck/head, hand endpoints, chest/shoulder cross sticks, and leg sticks use shoulder or hip lateral lines as roll references so two-point sticks do not twist unpredictably around their main axis.
- Bind-pose stability: when animation mode records skinning local offsets, it prefers the canonical pose captured when the skeleton/model was loaded, and restores voxels to their canonical positions first. This prevents one animation's skinned voxel positions from contaminating the next animation switch.
- Oriented voxel rendering: in animation mode each voxel cube's orientation rotates with its bone, eliminating the "staircase" silhouette at non-90° rotations. GPU data flows through a per-bone uniform — even 100k voxels only need 8 KB per frame.

### Planned

- Mixamo animation import (the "Import Mixamo" toolbar button is currently disabled)

## How to Use build.bat

`build.bat` is the one-click packaging script for the project. It produces a Windows distributable directory.

Run it with:

```bat
build.bat
```

It automatically:

1. Checks whether `.venv` exists
2. Activates the virtual environment
3. Installs `PyInstaller` if missing
4. Deletes old `build/` and `dist/` directories
5. Rebuilds the release package using [rwrsb_bind.spec](rwrsb_bind.spec)

After a successful build, the output is at:

```text
dist\rwrsb_bind\rwrsb_bind.exe
```

When distributing, it is recommended to zip the entire `dist\rwrsb_bind` folder rather than just the exe, because the directory also contains:

- PyInstaller runtime files
- `shaders/`
- `presets/`
- `glfw3.dll` and other bundled resources

## Editing Workflow

1. Open a `.vox` or `.xml` file
2. Inspect or edit the skeleton in the right panel
3. Add, modify, or delete `particle` / `stick` entries
4. Use `brush` or `voxel_select` for voxel binding
5. Drag particles in the viewport to fine-tune the skeleton
6. Save as XML
7. Optionally save the current skeleton as a preset

## Editing Notes

- A `particle` is a skeleton node containing position and metadata.
- A `stick` connects two particles and corresponds to one binding constraint group.
- Binding relationships depend on `constraintIndex`.
- `constraintIndex` must stay consistent with the current stick order.
- When deleting or reordering sticks, the binding map must be updated in sync.
- Grid step sizes: `0.5`, `1`, or any positive integer in voxels.
- Grid planes can be enabled individually: `XZ / XY / YZ`.
- Viewport particle dragging supports axis constraints:
  - `Shift`: lock X
  - `Ctrl`: lock Y
  - `Alt`: lock Z

## Project Structure

The project is still a flat Python tool repository. Runtime code lives in the repository root, with resources grouped into a few purpose-specific directories:

| Path | Responsibility |
|------|----------------|
| `main.py` | Binding tool entry point (`rwrsb_bind.exe`); GLFW loop, viewport input, voxel binding, bone-edit gizmo |
| `main_animation.py` | Animation tool entry point (`rwrsb_anim.exe`); playback tick, keyframe editing, animation viewport interaction |
| `editor_state.py` | Core state center; voxels / particles / sticks / bindings, undo/redo, presets, animation mode, skinning, canonical bind pose |
| `ui_panels.py` | ImGui panels, popups, toolbar, bilingual text, toasts, gizmo pivot selector, animation timeline UI |
| `renderer.py` | OpenGL rendering; voxels, skeleton, particles, grid, gizmo, oriented-voxel shader data upload |
| `animation_io.py` | Soldier animation XML parsing, writing, indexing, interpolation, and `Animation` / `AnimationFrame` data classes |
| `xml_io.py` | `.vox` parsing, project XML parsing/writing, RWR/MagicaVoxel coordinate conversion |
| `camera.py` | Orbit / Ortho camera, view presets, screen-ray construction |
| `file_dialogs.py` | Windows open/save file dialog wrapper |
| `logger_setup.py` | Log directory, file logging, and default logger initialization |
| `resource_utils.py` | Resource path resolution for source runs and PyInstaller builds |
| `build.bat` / `setup.bat` / `run.bat` | Environment setup, development launch, and packaging scripts |
| `rwrsb_bind.spec` / `rwrsb_anim.spec` | PyInstaller packaging configs |
| `presets/` | Skeleton preset JSON files |
| `shaders/` | GLSL shaders |
| `docs/` | Public documentation assets such as README screenshots |

Local debug material and AI collaboration material are not part of the release structure: `logs/`, `claude_use/`, `history/`, `.claude/worktrees/`, and temporary XML samples should normally stay out of release commits.

## XML Data Model

The XML workflow revolves around three data blocks:

- `voxels` — voxel positions and colors
- `skeleton`
  - `particle`
  - `stick`
- `skeletonVoxelBindings`
  - `group constraintIndex="..."`
  - Voxel indices belonging to a given stick group

Key constraints:

- Particle IDs must be unique.
- Both ends of a stick must reference existing particles.
- `group.constraintIndex` must equal the stick's list index.
- After editing the skeleton, the correct binding relationships must be preserved on export.

## Presets

Skeleton presets are stored as JSON files under `presets/`.

The repository currently ships with:

- `human_skeleton.json`
- `88.json`

Presets only store the skeleton structure:

- particles
- sticks

Voxel bindings are project-specific data and are not part of a preset.

## Developer Notes

- On a new machine, run `setup.bat` first.
- `.venv/` is local-only; do not commit it.
- Do not commit `__pycache__/`.
- If you change parsing or export logic, test at least one `.vox` and one `.xml` round-trip.
- Coordinate conversion changes are especially risky — they affect both import and export.
- Stick deletion and reordering are the most common sources of binding corruption; test carefully.

## Notes for AI Continuators

If you need to extend this project, read these first:

- [main.py](main.py)
- [editor_state.py](editor_state.py)
- [xml_io.py](xml_io.py)
- [ui_panels.py](ui_panels.py)

Recommended module boundaries:

- `editor_state.py` — state and business rules
- `renderer.py` — rendering and picking
- `ui_panels.py` — UI calls only; do not re-implement business logic here
- `xml_io.py` — file format parsing and writing

If you change skeleton logic, always verify together:

- Viewport dragging
- Panel editing
- Preset save/load
- Undo/redo
- XML export
- Binding remap after stick deletion

## Git Hygiene

The repository ignores these local artifacts:

```gitignore
.venv/
__pycache__/
*.py[cod]
build/
dist/
```

If these files are accidentally tracked later, remove them from the Git index rather than deleting the local files.

## Releases

Release process: see [docs/release/RELEASE_EN.md](docs/release/RELEASE_EN.md).

Release notes: see [docs/release/notes/RELEASE_NOTES_v1.1.1_EN.md](docs/release/notes/RELEASE_NOTES_v1.1.1_EN.md) (history: [v1.1.0](docs/release/notes/RELEASE_NOTES_v1.1.0_EN.md) / [v1.0.0](docs/release/notes/RELEASE_NOTES_v1.0.0_EN.md) / [v0.1.0](docs/release/notes/RELEASE_NOTES_v0.1.0.md)).

## Known Limitations

- Final runtime behavior should still be verified in a local OpenGL environment.
- Current XML compatibility targets this project's format, not an arbitrary generic schema.
- The current distribution is a directory package, not a single-file exe.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
