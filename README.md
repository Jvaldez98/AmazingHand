# AmazingHand team project

Desktop control and webcam teleoperation for the four-finger AmazingHand.
Each teammate runs the software on their own computer and plugs the hand's
controller into that computer by USB. No remote desktop or server is needed.

## First-time Windows setup

1. Install **64-bit Python 3.11** from https://www.python.org/downloads/windows/.
   Include the Python Launcher and Tcl/Tk (the standard installer includes Tk).
2. Download this repository using **Code > Download ZIP** and extract it fully,
   or clone it with Git. Keep the entire directory structure together.
3. Double-click **setup_windows.bat**. Internet access is required to install
   dependencies. Wait for the "Setup complete" message.
4. Connect the hand using its existing power arrangement and a USB data cable.
5. Launch the GUI matching the controller below and select the computer's
   actual COM port. COM3/COM4/COM9 are examples, not fixed assignments.

| Controller connected by USB | Launcher |
| --- | --- |
| ESP32 / TetherIA / Chestnut board with AmazingHand SCS0009 firmware | `launch_tether_gui.bat` |
| Waveshare direct USB bus-servo adapter | `launch_usb_gui.bat` |

The ESP32 GUI uses 921600 baud; the direct servo adapter normally uses 1000000.
Changing computers does not require reflashing an already configured controller.
Do not flash stock Aero firmware onto the AmazingHand SCS0009 setup.

## First connection and handoff

- Close other GUIs, serial monitors, and teleoperation programs before connecting.
  Only one process can own the USB serial port.
- Support the hand, keep its travel clear, and start with small movements.
- In the Tether GUI, connect first; torque starts disabled. Arm only when ready.
  Disarm and disconnect before moving the USB cable to another computer.
- Keep servo IDs, mechanical calibration, motor direction, and travel limits
  consistent with the physical hand. Switching laptops is not a reason to
  reassign IDs or reset neutral positions.
- If no COM port appears, try a USB data cable and check Windows Device Manager.
  Install a controller driver from its manufacturer only if Windows requires it.
- If setup or launch fails, the window stays open with the error. Check Python
  3.11 is installed, then rerun setup. Do not copy another person's virtual environment.

## Webcam teleoperation

See [TELEOP_README.md](TELEOP_README.md) for calibration, controls, and both
transports. After team setup, substitute `.venv-team` for `.venv-teleop` in
those commands. Start with mock mode:

```powershell
.\.venv-team\Scripts\python.exe .\amazing_hand_teleop.py --mock --verbose --force-webcam
```

Close the GUI before running hardware teleoperation. Webcam control starts
disarmed; verify tracking and calibration before arming.

## Files and team changes

Share the Python sources, `grasps/`, `teleop_vision/`, tests, firmware, and both
reference directories. Keep their license and attribution files intact.
`requirements.txt` installs dependencies for both GUIs and webcam teleoperation.
Python environments, caches, credentials, and local application settings are
excluded from Git. Saved poses in `data/hand_config.yaml`, if created, can be
shared deliberately; review hardware-specific settings before using them.

For a private GitHub repository, its owner adds teammates under **Settings >
Collaborators**. Teammates can download ZIPs or clone the repository, and use
branches/pull requests for changes. Pull updates with control programs closed;
rerun setup when dependencies change.

## Included upstream projects

- `tetheria_reference/`: local reference copy from
  https://github.com/Jvaldez98/aero_webcam_teleop
- `tetheria_amazinghand/`: local reference copy from
  https://github.com/Chestnut-Robotics/aero-hand-open, including AmazingHand firmware changes.

These directories must be included as ordinary files in a team release, not
empty Git links. Their original nested Git histories and local environments
are not needed to run the project. Existing upstream license notices apply.
