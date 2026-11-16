# AmazingHand webcam teleoperation

This is a first, safety-oriented webcam teleoperation mode for the four-finger
AmazingHand. It reuses the MediaPipe capture and retargeting logic in the
linked `tetheria_reference` repository, but replaces the Aero/ESP32 bridge
with the existing `rustypot` Waveshare USB bus-servo controller.

## Safety behavior

- The program always starts **disarmed**.
- Camera tracking must be stable for five frames before commands are sent.
- Pressing Space toggles live control.
- Losing the tracked hand for 0.5 seconds opens the robot and disarms control.
- Closing the program disables torque on all eight servos.
- Thumb side-to-side control is disabled initially because its physical
  direction must be verified on the specific hand.

Keep the existing AmazingHand GUI closed while running teleoperation. Only one
program should own the serial adapter at a time.

## Environment

Use standard 64-bit CPython 3.11 on Windows. The old `.venv` currently in
this directory points to a Python installation that no longer exists, so use
a new environment name after installing/reinstalling Python 3.11 from
python.org (enable the Python Launcher during installation):

```powershell
py -3.11 -m venv .venv-teleop
.\.venv-teleop\Scripts\python.exe -m pip install --upgrade pip
.\.venv-teleop\Scripts\python.exe -m pip install -r requirements-teleop.txt
```

The MediaPipe version is intentionally pinned to `0.10.21`. The vision code
uses the legacy Hands/Solutions API, which is not available in MediaPipe 1.x.

## Test without hardware

```powershell
.\.venv-teleop\Scripts\python.exe .\amazing_hand_teleop.py --mock --verbose --force-webcam
```

In the camera window:

- `c`: calibrate while holding an open, flat palm
- `Space`: arm/disarm live teleoperation
- `o`: disarm and open the robot
- `f`: disarm and close the robot
- `q` or `Esc`: quit

Mock mode prints changed targets and never accesses the servo adapter.

## Run with AmazingHand

After verifying the preview and target values in mock mode, close the existing
GUI and run (replace `COM9` if necessary):

```powershell
.\.venv-teleop\Scripts\python.exe .\amazing_hand_teleop.py --port COM4 --force-webcam
```

Leave `--thumb-side-gain` at its default of `0` for the first hardware test.
Flexion will still control all four fingers. Thumb lateral motion can be tested
later at a low gain such as `--thumb-side-gain 0.15`; add
`--invert-thumb-side` if its direction is reversed.

## Run through the TetherIA/Chestnut PCB

First flash the AmazingHand-specific firmware from
`tetheria_amazinghand/firmware/amazinghand_scs0009`. Do not use the stock Aero
HLS3606M firmware with the SCS0009 servos.

Assign IDs and test each servo using:

```powershell
.\.venv-teleop\Scripts\python.exe .\amazinghand_tether_gui.py
```

Then run webcam control through the ESP32 USB-C port:

```powershell
.\.venv-teleop\Scripts\python.exe .\amazing_hand_teleop.py --transport tether --port COM3 --force-webcam
```

If all four servo pairs rotate in the mechanically opposite direction, stop
the program and add `--reverse-motors`. This changes only host-side signs and
does not require reflashing firmware:

```powershell
.\.venv-teleop\Scripts\python.exe .\amazing_hand_teleop.py --transport tether --port COM3 --force-webcam --reverse-motors
```

The ESP32 USB connection uses 921600 baud; the servo bus uses 1000000 baud.
Firmware boots with torque disabled. The webcam bridge enables torque only
when it sends the first explicit motion target and disables it when closing.

## Finger spread (abduction/adduction)

Pointer, middle, and ring spread can be enabled independently of motor reversal:

```powershell
.\.venv-teleop\Scripts\python.exe .\amazing_hand_teleop.py --transport tether --port COM3 --force-webcam --finger-side-gain 0.25
```

Replace COM3 with your ESP32 port. Keep `--reverse-motors` omitted if curling
already works correctly. First try the same command with `--mock --verbose`
to inspect targets without moving hardware.

Hold an open palm facing the camera with fingers comfortably together, then
press `c` to record neutral spacing. Press Space to arm, then spread your fingers.
Spread stays disabled until a valid calibration. It uses each finger's proximal
segment relative to the palm, with smoothing and a small deadband. Keep the palm
facing the camera: edge-on poses and curled fingers make image spread unreliable.
The existing servo-pair interpolation reduces sideways travel as curl increases
and removes it at full closure.

`--finger-side-gain` ranges from 0 (default, disabled) to 1. Start at 0.25 and
verify mechanical travel before increasing it. This is a software mapping of
the existing GUI side controls; its physical range has not been verified on
your hand. If an individual finger moves sideways in the opposite direction,
set its sign in pointer/middle/ring order, for example:

```powershell
--finger-side-directions -1 1 -1
```

If spread is reversed for all three fingers, use `--finger-side-directions -1 -1 -1`.
Sensitivity can also be tuned independently with `--finger-side-ranges 25 12 12`
(pointer/middle/ring). Smaller ranges reach the same output with less human
movement; they do not increase the maximum motor command set by gain. Each value
must exceed the three-degree deadband. These are angles in the image palm basis,
not measured anatomical joint angles. The camera overlay shows `side=` for each
finger so you can distinguish weak tracking input from weak mechanical motion.
The middle finger may move little during a natural spread; sensitivity only
amplifies movement that the camera detects.

Thumb closure uses thumb-tip distance to the palm center after pressing `c`.
Calibrate with your palm facing the camera and your thumb comfortably extended.
Moving the thumb toward the palm closes it, reaching full closure at 35% of
the calibrated open distance while retaining the existing servo limits.
Index fingertip movement does not enter this measurement. Before calibration,
or when the palm geometry is invalid, the original joint-angle mapping is used.

Thumb sideways control remains separate: use `--thumb-side-gain 0.15` and,
if needed, `--invert-thumb-side`.

