# VirtualCom Installation and Build Guide

This document describes how to install, run, and build VirtualCom for **Windows** and **macOS**.

---

## Versioning (Important)

Single source of truth:
- `pyproject.toml` (`[project].version` + `[tool.virtualcom].release_date`)

Before any installer build (Windows/macOS), check version sync.

macOS/Linux:

```bash
python3 scripts/update_version.py status | cat
```

Windows:

```powershell
python scripts\update_version.py status
```

If status contains `[MISMATCH]`, run sync first.

macOS/Linux:

```bash
python3 scripts/update_version.py sync | cat
```

Windows:

```powershell
python scripts\update_version.py sync
```

---

## Quick Start (Automated Build)

### Windows

Run:

```powershell
.\build_installer.bat
```

This will:
1. Validate version sync (fails on mismatch).
2. Create virtual environment (`venv`).
3. Install requirements and PyInstaller.
4. Build executable (`dist\VirtualCom.exe`).
5. Build installer (`output\VirtualCom_Setup_<version>.exe`) via Inno Setup.

### macOS

Run:

```bash
bash build_installer_mac.sh | cat
```

This will:
1. Create virtual environment (`venv_mac`).
2. Install requirements and PyInstaller.
3. Build executable (`dist_mac/VirtualCom`) and wrap into `VirtualCom.app`.
4. Create drag-and-drop DMG (`VirtualCom_Installer.dmg`) with `Applications` shortcut.

---

## Prerequisites

### Common
- Python 3.12+ available in PATH.

### Windows
- Inno Setup 6 (`ISCC.exe`) for `.exe` installer packaging.

### macOS
- No extra tools required (uses built-in `hdiutil`, `sips`, `iconutil`, `osascript`).

---

## Run From Source (Development)

### Windows

```powershell
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
venv\Scripts\python vicom.py
```

### macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 vicom.py
```

---

## Manual Build (If Needed)

### 1) Setup Environment

Windows:

```powershell
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt pyinstaller
```

macOS:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt pyinstaller
```

### 2) Build Executable (PyInstaller)

Windows:

```powershell
pyinstaller --clean --noconfirm --onefile --console --name VirtualCom vicom.py
```

Result: `dist\VirtualCom.exe`

macOS:

```bash
pyinstaller --clean --noconfirm --onefile --console --name VirtualCom vicom.py
```

Result: `dist/VirtualCom`

### 3) Package Installer

Windows (Inno Setup):

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer.iss"
```

Result: `output\VirtualCom_Setup_<version>.exe`

macOS (recommended script):

```bash
bash build_installer_mac.sh | cat
```

Result: `VirtualCom_Installer.dmg`

---

## Troubleshooting (Windows)

### "pip is not recognized"

Use:

```powershell
python -m pip install ...
```

or inside venv:

```powershell
venv\Scripts\python -m pip install ...
```

### "ISCC.exe not found"

Install Inno Setup 6 or update path in `build_installer.bat`.

### "Version files are out of sync"

Run:

```powershell
python scripts\update_version.py sync
.\build_installer.bat
```

### PowerShell execution policy blocks activation

Use direct interpreter call:

```powershell
.\venv\Scripts\python.exe vicom.py
```

---

## Build-Related Files

- `vicom.py` - Main application script.
- `requirements.txt` - Python dependencies.
- `pyproject.toml` - Source of truth for version/date.
- `scripts/update_version.py` - Version sync CLI.
- `version_info.py` - Runtime version data (derived).
- `build_installer.bat` - Windows build script.
- `installer.iss` - Windows Inno Setup config.
- `build_installer_mac.sh` - macOS build/DMG script.
