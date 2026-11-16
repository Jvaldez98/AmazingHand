@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-team\Scripts\python.exe" (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
".venv-team\Scripts\python.exe" amazinghand_tether_gui.py
if errorlevel 1 pause
