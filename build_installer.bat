@echo off
setlocal
chcp 65001 >nul

cd /d "%~dp0"

echo [1/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.13+ and add it to PATH.
    exit /b 1
)

echo [2/6] Preparing venv...
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
)

echo [3/6] Installing dependencies...
call "venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

call "venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

echo [4/6] Building EXE (PyInstaller)...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

call "venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm --onefile --console --name VirtualCom vicom.py
if errorlevel 1 exit /b 1

echo [5/6] Checking Inno Setup (ISCC)...
set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_EXE%" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not exist "%ISCC_EXE%" (
    echo [ERROR] ISCC.exe not found. Install Inno Setup 6.
    echo Expected path: "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    exit /b 1
)

echo [6/6] Building installer...
"%ISCC_EXE%" "installer.iss"
if errorlevel 1 exit /b 1

echo.
echo Done. Installer is available in "output".
exit /b 0
