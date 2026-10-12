@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First install the project using the README commands.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m blini.gui
if errorlevel 1 pause
