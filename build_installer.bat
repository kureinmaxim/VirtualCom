@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

echo [1/7] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.13+ and add it to PATH.
    exit /b 1
)

echo [2/7] Checking version sync...
python scripts\update_version.py status | findstr /C:"[MISMATCH]" >nul
if not errorlevel 1 (
    echo [ERROR] Version files are out of sync. Run:
    echo         python scripts\update_version.py sync
    exit /b 1
)

echo [3/7] Preparing venv...
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
)

echo [4/7] Installing dependencies...
call "venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

call "venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

echo [5/7] Building EXE (PyInstaller)...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

set "PYI_ICON_ARG="
if exist "assets\icons\virtualcom.ico" (
    set "PYI_ICON_ARG=--icon assets\icons\virtualcom.ico"
    echo [INFO] Using icon: assets\icons\virtualcom.ico
)

call "venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm --onefile --console --name VirtualCom %PYI_ICON_ARG% vicom.py
if errorlevel 1 exit /b 1

echo [6/7] Checking Inno Setup (ISCC)...
set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_EXE%" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not exist "%ISCC_EXE%" (
    echo [ERROR] ISCC.exe not found. Install Inno Setup 6.
    echo Expected path: "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    exit /b 1
)

echo [7/7] Building installer...
"%ISCC_EXE%" "installer.iss"
if errorlevel 1 exit /b 1

echo.
echo Done. Installer is available in "output".
exit /b 0
