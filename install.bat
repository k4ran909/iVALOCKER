@echo off
REM Installs everything iVALOCKER needs to run and build (run once, and again after
REM requirements.txt changes). Requires Python 3.9+ on PATH. See BUILDING.md.
cd /d "%~dp0"
python --version >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.9+ from https://www.python.org/downloads/windows/
    echo and tick "Add python.exe to PATH" during setup. See BUILDING.md for details.
    pause
    exit /b 1
)
python install_and_build\install.py
pause
