@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Install dependencies first. See DALION_DEMO.md.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "dalion_demo.py"
