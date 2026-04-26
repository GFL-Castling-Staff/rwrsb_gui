# rwrsb_bind v1.0.0 Release Notes

> [中文版](RELEASE_NOTES_v1.0.0.md)

## Breaking Change: Tool Renamed

`rwrsb_gui.exe` has been renamed to **`rwrsb_bind.exe`**.

The old name `rwrsb_gui` was too ambiguous (both tools are GUI applications). `rwrsb_bind` more directly communicates the actual purpose of "skeleton binding editor". The v1.0.0 version bump signals this breaking change.

**Recommended upgrade steps:**

1. Download the new `rwrsb_bind-v1.0.0-windows.zip` and extract it to any directory.
2. Manually delete the old `dist\rwrsb_gui\` directory (optional — it does not affect the new version, but it will not be cleaned up automatically).
3. Replace any desktop shortcuts or launch scripts with the new `rwrsb_bind.exe`.

The log directory is unchanged (still at `%LOCALAPPDATA%\rwrsb_gui\logs\` or `logs\` next to the exe). Historical logs are unaffected.

---

## Changes in This Release

### Documentation and Standards

- Added `LICENSE` (MIT, 2025–2026, SAIWA)
- Added `ARCHITECTURE.md`: 9-section architecture overview covering EditorState field groups, `tool_mode` three-state semantics, modifier key reference table, animation mode transitions, five dirty flags, and other implicit knowledge
- Added `CONTRIBUTING.md`: bug reporting / feature suggestion / pull request workflow
- `README.md`: fixed hardcoded local paths, added screenshot placeholder (replace `docs/screenshot.png` with an actual screenshot)
- `editor_state.py`: EditorState class docstring (9 groups); docstrings on `_snapshot` / `_restore_snapshot` / `StickEntry.clone` explaining the `visible` channel design decision
- `ui_panels.py`: UIState class docstring
- `camera.py`: OrbitCamera class docstring
- `xml_io.py`: type annotations on `parse_vox` / `parse_xml` / `write_xml`
- `renderer.py`: type annotations on `box_select_voxels` / `pick_particle_screen` / `box_select_particles`

### Rename (Breaking Change)

- `rwrsb_gui.spec` → `rwrsb_bind.spec`
- Window title `rwrsb v2.0` → `rwrsb_bind v1.0.0`
- All tool name references in `build.bat`, `README.md`, and `RELEASE.md` updated accordingly
- Log path in `logger_setup.py` **intentionally keeps** `rwrsb_gui` to avoid stranding historical logs

---

## Actions Required from the Project Owner Before Release

- [ ] Run `python main.py`, screenshot the main editor window, save as `docs/screenshot.png`, delete `docs/screenshot.placeholder.txt`
- [ ] Run `build.bat`, confirm output is at `dist\rwrsb_bind\rwrsb_bind.exe`
- [ ] Launch `dist\rwrsb_bind\rwrsb_bind.exe`, confirm the window title shows `rwrsb_bind v1.0.0`
- [ ] Launch `dist\rwrsb_anim\rwrsb_anim.exe` (or `python main_animation.py`), confirm the animation tool is unaffected
- [ ] Grep `rwrsb_gui` in the repo root, confirm only `RELEASE_NOTES_v0.1.0.md` (historical) and `logger_setup.py` (intentional) remain
