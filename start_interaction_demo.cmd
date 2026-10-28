@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Install dependencies first. See INTERACTION_FEATURES.md.
    pause
    exit /b 1
)
set "interactionDataDir=%LOCALAPPDATA%\RusskieBliny-InteractionDemo"
start "" ".venv\Scripts\pythonw.exe" "app.py" "--data-dir" "%interactionDataDir%"
