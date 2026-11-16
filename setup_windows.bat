@echo off
setlocal
cd /d "%~dp0"
echo Setting up AmazingHand for this computer...
py -3.11 -c "import sys; assert sys.maxsize > 2**32" >nul 2>&1
if errorlevel 1 (
  echo Install 64-bit Python 3.11 from python.org, including the Python Launcher.
  echo Then run this file again. See README.md.
  pause
  exit /b 1
)
if not exist ".venv-team\Scripts\python.exe" (
  py -3.11 -m venv .venv-team
  if errorlevel 1 goto failed
)
".venv-team\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto failed
".venv-team\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv-team\Scripts\python.exe" -c "import tkinter, serial, numpy, yaml, matplotlib, cv2, mediapipe, rustypot; assert hasattr(mediapipe, 'solutions')"
if errorlevel 1 goto failed
echo Setup complete. Use launch_tether_gui.bat or launch_usb_gui.bat.
pause
exit /b 0
:failed
echo Setup failed. Read the error above before closing this window.
pause
exit /b 1
