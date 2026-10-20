# Packaging Plan

## Options compared
- PyInstaller onedir + Inno Setup (chosen): mature, supports data files, job objects, easy installer.
- Nuitka: better performance but longer build, more complexity.
- MSIX: sandboxed, harder for CLI PATH and process supervision.
- WiX: verbose, more maintenance.

## Choice
PyInstaller onedir + Inno Setup. No UPX (AV false positive risk). No onefile (process supervision and AV impact).