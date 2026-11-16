# AmazingHand firmware for the TetherIA/Chestnut PCB

This is a separate, safety-first firmware variant for eight Feetech SCS0009
servos. It does not use the Aero Hand HLS3606M homing routine or HLS register
map.

## Safety behavior

- Servo bus: 1,000,000 baud; expected IDs: 1 through 8.
- USB host protocol: 921,600 baud; fixed 16-byte frames.
- Torque is disabled at boot.
- Motion speed defaults to level 6 (the fastest AmazingHand setting) and can be
  changed from 1 through 6 in the GUI.
- ID assignment accepts only IDs 1 through 8 and refuses to continue unless
  exactly one servo is detected.
- The ID operation changes only the SCS0009 ID register. It intentionally does
  not write the HLS current-limit register.

## Build and upload

Open this folder in VS Code with PlatformIO, connect the XIAO ESP32-S3 USB-C
port, and use **PlatformIO: Upload**. Do not upload the stock Aero firmware to
the AmazingHand servos.

The build downloads Feetech's official `FTServo_Arduino` library.

The verified application binary is `firmware_amazinghand_scs0009.bin`. It can
be selected in the original TetherIA GUI's firmware uploader, which writes an
application binary at offset `0x10000`, or uploaded from this repository with:

```powershell
.\.venv-teleop\Scripts\python.exe -m platformio run `
  -d .\tetheria_amazinghand\firmware\amazinghand_scs0009 `
  -t upload --upload-port COM3
```

Replace `COM3` with the XIAO ESP32-S3's port. The PlatformIO board definition
enables native USB CDC automatically.

## ID assignment

Connect the board to regulated 6 V servo power and connect exactly one servo.
Use `amazinghand_tether_gui.py`, assign the appropriate ID, disconnect and
label the servo, then repeat. Connect the full bus only after all eight IDs are
unique.

Mapping: pointer 1/2, middle 3/4, ring 5/6, thumb 7/8.

## Safe manual homing/calibration

Do not use the Aero firmware's force/current-based homing routine on this
mechanism. In the AmazingHand GUI, use **Teach open/zero pose**:

1. Leave torque disabled and support the mechanism.
2. Manually position all connected fingers in their open, centered pose.
3. Click **Teach open/zero pose** and confirm.
4. The ESP32 reads each responding SCS0009 and stores that raw position as the
   servo's logical 0 degrees in NVS.
5. Clear the mechanism, arm torque, and use **Home (calibrated zero)**.

The offsets persist across power cycles and ordinary firmware updates. The
**Reset calibration** button restores raw midpoint 511 for all motors.

The speed selector intentionally matches the original Python/rustypot GUI.
Levels 1 through 6 represent radians per second and are converted to the
SCS0009 raw goal-speed register; they are not written as raw values 1 through
6.

