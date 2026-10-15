@echo off
REM Builds the PORTABLE app: dist\iVALOCKER_k4ran909.exe (single exe, no install).
REM Run install.bat once first. See BUILDING.md.
cd /d "%~dp0"
python --version >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.9+ from https://www.python.org/downloads/windows/
    echo and tick "Add python.exe to PATH" during setup. See BUILDING.md for details.
    pause
    exit /b 1
)
python install_and_build\build.py
pause
