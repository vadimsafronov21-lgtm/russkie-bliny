@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "launch.py" %*
  goto done
)
where py >nul 2>nul
if not errorlevel 1 (
  for %%V in (3.13 3.12 3.11) do (
    py -%%V -c "import sys; assert (3,11) <= sys.version_info[:2] <= (3,13)" >nul 2>nul
    if not errorlevel 1 (
      py -%%V "launch.py" %*
      goto done
    )
  )
)
where python >nul 2>nul
if not errorlevel 1 (
  python -c "import sys; assert (3,11) <= sys.version_info[:2] <= (3,13)" >nul 2>nul
  if not errorlevel 1 (
    python "launch.py" %*
    goto done
  )
)
echo Не найден Python 3.11, 3.12 или 3.13.
echo Установите 64-битный Python с https://www.python.org/downloads/windows/
echo При установке включите Add python.exe to PATH, затем снова откройте start.bat.
echo Подробная инструкция: НАЧНИ_ЗДЕСЬ.md
pause
exit /b 1
:done
if errorlevel 1 (
  echo.
  echo Запуск завершился с ошибкой. Текст ошибки показан выше.
  pause
  exit /b 1
)
exit /b 0
