# Release Guide

## Recommended Release Flow

1. Make sure the repository is clean.
2. Test the app from source with `run.bat`.
3. Build the Windows package with `build.bat`.
4. Test `dist\rwrsb_gui\rwrsb_gui.exe` on the build machine.
5. Zip the whole `dist\rwrsb_gui` folder.
6. Create a Git tag such as `v0.1.0`.
7. Create a GitHub Release and upload the zip.

## Suggested Release Notes Template

### Highlights

- Load `.vox` and supported XML files
- Particle / stick skeleton editing
- Viewport particle dragging
- Grid display and grid snapping
- Chinese / English UI
- UI scaling and invert-Y camera option

### Known Limitations

- Windows only
- Requires working OpenGL drivers
- Packaged build is directory-based, not single-file

## Release Artifact

Recommended upload:

- `rwrsb_gui-vX.Y.Z-windows.zip`

The zip should contain:

- `rwrsb_gui.exe`
- bundled Python runtime files from PyInstaller
- `shaders/`
- `presets/`
