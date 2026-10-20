@echo off
cd /d "%~dp0"
if exist "dist\RusskieBliny.exe" (
  start "" "dist\RusskieBliny.exe"
) else (
  ".venv\Scripts\python.exe" app.py
)
