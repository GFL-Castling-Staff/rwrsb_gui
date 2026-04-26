# Release Guide

> [中文版](RELEASE.md)

This document explains how to prepare a GitHub Release from the current project.

## Recommended Release Process

1. Confirm the working directory is clean with no unexpected changes.
2. Run from source once to verify basic functionality.
3. Run `build.bat` to generate the Windows distribution package.
4. Test `dist\rwrsb_bind\rwrsb_bind.exe` locally.
5. Zip the entire `dist\rwrsb_bind` folder.
6. Confirm the version number and tag, e.g., `v0.1.0`.
7. Create a Release on GitHub.
8. Upload the zip package and paste the corresponding release notes.

## What build.bat Does

`build.bat` is the standard packaging entry point for the project.

It automatically:

1. Checks whether the virtual environment exists
2. Activates `.venv`
3. Installs `PyInstaller` if missing
4. Cleans up old `build/` and `dist/` directories
5. Rebuilds the distribution package using [rwrsb_bind.spec](rwrsb_bind.spec)

Run it with:

```bat
build.bat
```

Output:

```text
dist\rwrsb_bind\rwrsb_bind.exe
```

Note:

- When distributing, zip the entire `dist\rwrsb_bind` folder — do not ship the exe alone.
- The directory also contains `_internal/`, asset files, and dependency DLLs required at runtime.

## Recommended Release Artifacts

Suggested file name:

- `rwrsb_bind-v1.0.0-windows.zip`

The zip should include:

- `rwrsb_bind.exe`
- PyInstaller-generated `_internal/`
- `shaders/`
- `presets/`

## Suggested Release Page Content

Suggested title:

- `rwrsb_bind v1.0.0`

Suggested body:

- Use [RELEASE_NOTES_v1.0.0_EN.md](RELEASE_NOTES_v1.0.0_EN.md) directly.

## Pre-Release Checklist

- [ ] `.vox` loading works correctly
- [ ] `.xml` loading works correctly
- [ ] XML export works correctly
- [ ] Particle dragging works correctly
- [ ] Grid display and snapping work correctly
- [ ] Chinese / English switch works correctly
- [ ] UI scaling works correctly
- [ ] Y-axis inversion works correctly
- [ ] Preset save and load work correctly
- [ ] The packaged exe starts correctly on the local machine

## Known Practical Issues

- Whether OpenGL applications run stably still depends on the target machine's drivers.
- Directory-based distributions are generally more stable than single-file distributions.
- If the target machine is missing system runtime libraries or has an abnormal GPU environment, additional troubleshooting may be required.
