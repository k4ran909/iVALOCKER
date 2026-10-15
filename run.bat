@echo off
cd /d "%~dp0"
if exist "dist\iVALOCKER_k4ran909.exe" (
    start "" "dist\iVALOCKER_k4ran909.exe"
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" main.py
) else (
    python main.py
)
