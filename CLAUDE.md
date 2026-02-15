# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VirtualCom is a single-file Python CLI application (`vicom.py`, ~660 lines) that emulates serial COM ports for device simulation and testing. It provides an interactive terminal interface for managing serial ports, sending/receiving data in multiple formats (text, HEX, HEX+CRC16), and testing Modbus CRC16 implementations. Cross-platform: Windows and macOS.

## Build & Run Commands

### Run from source
```bash
# Create venv and install deps
python3 -m venv venv && source venv/bin/activate  # macOS/Linux
python -m venv venv && venv\Scripts\activate       # Windows
pip install -r requirements.txt
python vicom.py
```

### Build installers
```bash
# macOS — produces VirtualCom_Installer.dmg
bash build_installer_mac.sh

# Windows — produces output/VirtualCom_Setup_1.1.0.exe
build_installer.bat
```

Both scripts create a venv, install pyserial + PyInstaller, build a single-file console executable via `pyinstaller --onefile --console --name VirtualCom vicom.py`, then package it (DMG on macOS, Inno Setup on Windows).

### No test suite exists
There are no automated tests. CRC16 calculation and serial logic are tested manually.

## Architecture

**Single-file app** with a two-thread model:
- **Main thread**: keyboard input loop, menu display, send operations
- **Receiver thread** (daemon): monitors serial port via `receive_data()`, displays incoming data in HEX+ASCII, calls `process_request()` for automated responses

Thread synchronization uses `threading.Event` (`processing_event`) — set to enable reception, clear to pause.

**Key function groups in `vicom.py`:**
- Port management: `select_port()`, `list_available_ports()`, `is_port_currently_available()`
- Configuration: `choose_configuration_mode()`, `full_port_configuration()` (default: 38400/8/N/1)
- Data transmission: `send_text_message()`, `send_hex_data()`, `send_hex_data_with_crc()`
- CRC16-MODBUS: `calculate_crc16()` using polynomial `0xA001`
- Request processing: `process_request()` handles predefined request→response mappings
- Cross-platform keyboard: `UnixGetch` class for macOS/Linux, `msvcrt` for Windows

**Cross-platform patterns:** `os.name == 'nt'` checks gate Windows-specific code. Keyboard input uses `msvcrt` on Windows and a custom `UnixGetch` class (using `tty.setraw` + `select`) on Unix.

## Dependencies

- **Runtime**: `pyserial>=3.5` (only external dependency)
- **Build**: PyInstaller, Inno Setup 6 (Windows only)
- **Python**: 3.12+

## Conventions

- Comments and user-facing strings are primarily in **Russian**
- Documentation is bilingual (Russian + English)
- App version is `1.1.0` (tracked in `installer.iss` and build scripts)
- Emoji characters are used in user-facing terminal output
