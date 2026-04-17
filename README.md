# rwrsb_gui

Voxel skeleton binding editor for RWR-style assets.

This tool can load `.vox` or project XML, edit skeleton structure and voxel bindings, and export back to the target XML format. The current codebase is focused on a practical desktop workflow for adding, modifying, and reusing skeletons instead of only rebinding an existing human preset.

## What It Can Do

- Load MagicaVoxel `.vox` files
- Load supported XML files with voxels, skeleton, and bindings
- Edit `particle` nodes
- Edit `stick` connections
- Rebind voxels to skeleton groups
- Save and reuse skeleton presets from `presets/`
- Drag particles directly in the viewport
- Snap particles to a configurable grid
- Show orthographic helper grids on `XZ`, `XY`, and `YZ` planes
- Export the edited result as XML

## Requirements

- Windows
- Python 3.10+
- OpenGL-capable GPU / driver

Python packages used by the app:

- `moderngl`
- `glfw`
- `imgui[glfw]`
- `numpy`

## Quick Start

Create the virtual environment and install dependencies:

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

You can also open a file immediately:

```bat
.venv\Scripts\python main.py path\to\model.vox
```

## Main Workflow

1. Load a `.vox` or `.xml` file.
2. Inspect or edit the skeleton in the right-side panels.
3. Create, modify, or delete `particle` and `stick` entries.
4. Bind voxels with brush/select tools.
5. Move particles in the viewport by direct dragging.
6. Save XML when the skeleton and bindings are ready.
7. Optionally save the current skeleton as a preset for reuse.

## Editing Notes

- `particle` is a skeleton node with position and metadata.
- `stick` connects two particles and becomes one binding constraint group.
- Binding groups rely on `constraintIndex`.
- `constraintIndex` must stay aligned with the current stick order.
- Deleting or reordering sticks should always keep bindings in sync.
- Grid snapping can use `0.5`, `1`, or any positive integer voxel step.
- Grid planes can be enabled independently for `XZ`, `XY`, and `YZ`.
- Particle drag supports axis locking:
  - `Shift`: X axis
  - `Ctrl`: Y axis
  - `Alt`: Z axis

## Project Structure

- `main.py`
  - Application entry point
  - Window lifecycle
  - Input handling
  - Particle dragging
  - Grid updates
- `editor_state.py`
  - Core editable project state
  - Undo/redo snapshots
  - Skeleton CRUD
  - Binding data
  - Preset CRUD
- `ui_panels.py`
  - ImGui panels and dialogs
  - Skeleton editing UI
  - Load/save dialogs
  - Grid and editing settings
- `renderer.py`
  - Voxel rendering
  - Skeleton rendering
  - Particle picking
  - Grid rendering
- `camera.py`
  - Orbit and orthographic camera behavior
  - View presets
  - Ray construction
- `xml_io.py`
  - `.vox` parsing
  - XML parsing
  - XML writing
  - Coordinate conversion helpers
- `presets/`
  - Skeleton preset JSON files
- `shaders/`
  - GLSL shader sources

## XML Model

The XML workflow is centered around three related blocks:

- `voxels`
  - Voxel positions and colors
- `skeleton`
  - `particle`
  - `stick`
- `skeletonVoxelBindings`
  - `group constraintIndex="..."`
  - voxel indices belonging to each stick group

Important invariants:

- Particle IDs must stay unique.
- Stick endpoints must reference valid particle IDs.
- Group `constraintIndex` must match the stick index.
- Export should preserve all active voxel bindings after skeleton edits.

## Presets

Skeleton presets are stored as JSON files in `presets/`.

Current repository presets:

- `human_skeleton.json`
- `88.json`

Presets store skeleton structure only:

- particles
- sticks

Voxel bindings are project-specific and are not treated as preset data.

## For Human Contributors

- Use `setup.bat` first on a fresh machine.
- Keep `.venv/` local only.
- Do not commit `__pycache__/`.
- Test loading both `.vox` and `.xml` if you change parsing or export code.
- Be careful with coordinate conversion changes; they affect both import and export.
- Be careful with stick deletion and reindexing; binding corruption usually starts there.

## For AI Contributors

When extending this project, start here:

- Read `main.py` to understand the runtime loop and input flow.
- Read `editor_state.py` before changing any skeleton behavior.
- Read `xml_io.py` before touching import/export assumptions.
- Read `ui_panels.py` for all editor-side controls and settings.

Expected architecture boundaries:

- `editor_state.py` should own editable data and mutations.
- `renderer.py` should draw and pick, not own project state rules.
- `ui_panels.py` should call state mutations, not duplicate business logic.
- `xml_io.py` should stay focused on file parsing/serialization.

When changing skeleton logic, verify these paths together:

- viewport drag
- panel editing
- preset save/load
- undo/redo
- XML export
- binding reindexing after stick edits

## Git Hygiene

This repository intentionally ignores generated local artifacts:

```gitignore
.venv/
__pycache__/
*.py[cod]
```

If these files ever get tracked by mistake again, remove them from the Git index instead of deleting local working files.

## Known Practical Limitations

- Runtime validation still depends on a local machine with working OpenGL and ImGui dependencies.
- XML compatibility is aimed at the current project format, not arbitrary unrelated schemas.
- The tool is desktop-oriented and not packaged as a standalone executable yet.
