"""Eight-servo AmazingHand setup/control GUI for the TetherIA ESP32 PCB."""

from __future__ import annotations

import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import serial
from serial.tools import list_ports


HOST_BAUD = 921_600
FRAME_SIZE = 16
OP_SET_ID = 0x02
OP_CALIBRATE_ZERO = 0x04
OP_RESET_CALIBRATION = 0x05
OP_CTRL_1_TO_7 = 0x11
OP_CTRL_8_COMMIT = 0x13
OP_ARM = 0x30
OP_DISARM = 0x31
OP_PING_ALL = 0x32
OP_SET_SPEED = 0x33

SERVO_LABELS = (
    "Pointer position",
    "Pointer side",
    "Middle position",
    "Middle side",
    "Ring position",
    "Ring side",
    "Thumb position",
    "Thumb side",
)

SET_ID_STATUS = {
    0: "success",
    1: "no servo detected",
    2: "multiple servos detected",
    3: "requested ID is already occupied",
    4: "EEPROM write verification failed",
    5: "ID must be between 1 and 8",
}


class TetherAmazingHand:
    """Thread-safe client for the AmazingHand ESP32 firmware."""

    def __init__(self, port: str, baudrate: int = HOST_BAUD, timeout: float = 0.1):
        self.serial = serial.Serial(port, baudrate, timeout=timeout, write_timeout=1.0)
        self.lock = threading.RLock()
        time.sleep(0.25)
        self.serial.reset_input_buffer()

    @staticmethod
    def _u16_frame(opcode: int, words: list[int] | tuple[int, ...]) -> bytes:
        padded = list(words[:7]) + [0] * (7 - len(words))
        return struct.pack("<BB7H", opcode, 0, *(value & 0xFFFF for value in padded))

    @staticmethod
    def _angle_frame(opcode: int, values: list[int] | tuple[int, ...]) -> bytes:
        padded = list(values[:7]) + [0] * (7 - len(values))
        return struct.pack("<BB7h", opcode, 0, *padded)

    def _wait_ack(self, opcode: int, timeout: float) -> tuple[int, ...]:
        deadline = time.monotonic() + timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            chunk = self.serial.read(FRAME_SIZE - len(buffer))
            if chunk:
                buffer.extend(chunk)
            if len(buffer) == FRAME_SIZE:
                if buffer[0] == opcode and buffer[1] == 0:
                    return struct.unpack("<7H", buffer[2:])
                del buffer[0]
        raise TimeoutError(f"No ACK received for opcode 0x{opcode:02X}")

    def _command(self, opcode: int, words: tuple[int, ...] = (), timeout: float = 3.0) -> tuple[int, ...]:
        with self.lock:
            self.serial.reset_input_buffer()
            self.serial.write(self._u16_frame(opcode, words))
            self.serial.flush()
            return self._wait_ack(opcode, timeout)

    def arm(self) -> None:
        self._command(OP_ARM)

    def disarm(self) -> None:
        self._command(OP_DISARM)

    def ping_all(self) -> int:
        return self._command(OP_PING_ALL)[0]

    def set_id(self, new_id: int) -> tuple[int, int, int]:
        if not 1 <= new_id <= 8:
            raise ValueError("Servo ID must be between 1 and 8")
        old_id, reported_id, status, *_ = self._command(OP_SET_ID, (new_id,), timeout=35.0)
        return old_id, reported_id, status

    def calibrate_zero(self, servo_id: int = 0) -> tuple[int, int, int]:
        if not 0 <= servo_id <= 8:
            raise ValueError("Calibration ID must be 0 (all) or 1 through 8")
        mask, first_raw, status, *_ = self._command(OP_CALIBRATE_ZERO, (servo_id,), timeout=8.0)
        return mask, first_raw, status

    def reset_calibration(self) -> None:
        status, *_ = self._command(OP_RESET_CALIBRATION)
        if status:
            raise RuntimeError(f"Calibration reset failed with status {status}")

    def set_speed(self, speed: int) -> int:
        if not 1 <= speed <= 6:
            raise ValueError("Speed must be between 1 and 6")
        reported, *_ = self._command(OP_SET_SPEED, (speed,))
        return reported

    def send_angles(self, degrees: list[float] | tuple[float, ...]) -> None:
        if len(degrees) != 8:
            raise ValueError("Expected eight servo angles")
        centidegrees = [
            max(-14900, min(14900, int(round(float(value) * 100.0))))
            for value in degrees
        ]
        with self.lock:
            self.serial.write(self._angle_frame(OP_CTRL_1_TO_7, centidegrees[:7]))
            self.serial.write(self._angle_frame(OP_CTRL_8_COMMIT, centidegrees[7:]))
            self.serial.flush()

    def close(self) -> None:
        with self.lock:
            if not self.serial.is_open:
                return
            try:
                self.serial.reset_input_buffer()
                self.serial.write(self._u16_frame(OP_DISARM, ()))
                self.serial.flush()
                self._wait_ack(OP_DISARM, 1.0)
            except Exception:
                pass
            self.serial.close()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AmazingHand - TetherIA PCB (8 x SCS0009)")
        self.geometry("900x700")
        self.client: TetherAmazingHand | None = None
        self.armed = False
        self.port_var = tk.StringVar()
        self.speed_var = tk.IntVar(value=6)
        self.status_var = tk.StringVar(value="Disconnected - torque disabled")
        self.angle_vars: list[tk.DoubleVar] = []
        self._build_ui()
        self.refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        connection = ttk.Frame(self, padding=10)
        connection.pack(fill=tk.X)
        ttk.Label(connection, text="ESP32 port:").pack(side=tk.LEFT)
        self.port_combo = ttk.Combobox(connection, textvariable=self.port_var, state="readonly", width=18)
        self.port_combo.pack(side=tk.LEFT, padx=6)
        ttk.Button(connection, text="Refresh", command=self.refresh_ports).pack(side=tk.LEFT)
        self.connect_button = ttk.Button(connection, text="Connect", command=self.connect)
        self.connect_button.pack(side=tk.LEFT, padx=8)
        self.disconnect_button = ttk.Button(connection, text="Disconnect", command=self.disconnect, state=tk.DISABLED)
        self.disconnect_button.pack(side=tk.LEFT)
        self.flash_button = ttk.Button(connection, text="Flash firmware", command=self.flash_firmware)
        self.flash_button.pack(side=tk.LEFT, padx=(12, 0))

        actions = ttk.Frame(self, padding=(10, 0, 10, 8))
        actions.pack(fill=tk.X)
        self.id_button = ttk.Button(actions, text="Assign one servo ID", command=self.assign_id, state=tk.DISABLED)
        self.id_button.pack(side=tk.LEFT, padx=(0, 8))
        self.scan_button = ttk.Button(actions, text="Check IDs 1-8", command=self.scan_ids, state=tk.DISABLED)
        self.scan_button.pack(side=tk.LEFT, padx=(0, 8))
        self.arm_button = ttk.Button(actions, text="ARM TORQUE", command=self.toggle_arm, state=tk.DISABLED)
        self.arm_button.pack(side=tk.LEFT, padx=(0, 8))
        self.calibrate_button = ttk.Button(
            actions, text="Teach open/zero pose", command=self.calibrate_open_pose, state=tk.DISABLED
        )
        self.calibrate_button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(actions, text="Home (calibrated zero)", command=self.open_targets).pack(side=tk.LEFT)

        settings = ttk.Frame(self, padding=(10, 0, 10, 4))
        settings.pack(fill=tk.X)
        ttk.Label(settings, text="Motion speed:").pack(side=tk.LEFT)
        self.speed_combo = ttk.Combobox(
            settings,
            textvariable=self.speed_var,
            values=(1, 2, 3, 4, 5, 6),
            width=4,
            state="readonly",
        )
        self.speed_combo.pack(side=tk.LEFT, padx=(6, 8))
        self.speed_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_speed())
        ttk.Label(settings, text="1 = slowest, 6 = fastest (recommended)").pack(side=tk.LEFT)
        self.reset_calibration_button = ttk.Button(
            settings, text="Reset calibration", command=self.reset_calibration, state=tk.DISABLED
        )
        self.reset_calibration_button.pack(side=tk.RIGHT)

        warning = (
            "ID setup: connect exactly ONE servo and regulated 6 V power. "
            "Connect the complete hand only after all IDs are unique."
        )
        ttk.Label(self, text=warning, foreground="#9b3d00", padding=(10, 4)).pack(fill=tk.X)

        sliders = ttk.LabelFrame(self, text="Eight SCS0009 motor angles", padding=10)
        sliders.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        for index, label in enumerate(SERVO_LABELS, start=1):
            row = ttk.Frame(sliders)
            row.pack(fill=tk.X, pady=4)
            ttk.Label(row, text=f"ID {index}: {label}", width=24).pack(side=tk.LEFT)
            variable = tk.DoubleVar(value=0.0)
            self.angle_vars.append(variable)
            scale = tk.Scale(
                row,
                from_=-120,
                to=120,
                resolution=1,
                orient=tk.HORIZONTAL,
                variable=variable,
                length=600,
                command=self._slider_changed,
            )
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=6).pack(fill=tk.X, side=tk.BOTTOM)

    def refresh_ports(self) -> None:
        ports = [port.device for port in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])

    def _set_connected_state(self, connected: bool) -> None:
        state = tk.NORMAL if connected else tk.DISABLED
        self.id_button.configure(state=state)
        self.scan_button.configure(state=state)
        self.arm_button.configure(state=state)
        self.calibrate_button.configure(state=state)
        self.reset_calibration_button.configure(state=state)
        self.disconnect_button.configure(state=state)
        self.connect_button.configure(state=tk.DISABLED if connected else tk.NORMAL)

    def connect(self) -> None:
        port = self.port_var.get()
        if not port:
            messagebox.showerror("Connection", "Select the ESP32 COM port first.")
            return
        try:
            self.client = TetherAmazingHand(port)
            self.armed = False
            self._set_connected_state(True)
            self.status_var.set(f"Connected to {port} at {HOST_BAUD} baud - torque disabled")
            self.apply_speed()
        except Exception as exc:
            messagebox.showerror("Connection failed", str(exc))

    def disconnect(self) -> None:
        client, self.client = self.client, None
        if client:
            client.close()
        self.armed = False
        self.arm_button.configure(text="ARM TORQUE")
        self._set_connected_state(False)
        self.status_var.set("Disconnected - torque disabled")

    def flash_firmware(self) -> None:
        default_binary = (
            Path(__file__).resolve().parent
            / "tetheria_amazinghand"
            / "firmware"
            / "amazinghand_scs0009"
            / "firmware_amazinghand_scs0009.bin"
        )
        binary = filedialog.askopenfilename(
            parent=self,
            title="Select AmazingHand ESP32 application firmware",
            initialdir=str(default_binary.parent),
            initialfile=default_binary.name,
            filetypes=(("ESP32 firmware", "*.bin"), ("All files", "*.*")),
        )
        if not binary:
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Flash firmware", "Select the XIAO ESP32-S3 COM port first.")
            return
        if not messagebox.askyesno(
            "Flash AmazingHand firmware",
            f"Flash {Path(binary).name} to the XIAO ESP32-S3 on {port}?\n\n"
            "Disconnect servo power before continuing. This replaces the firmware currently on the ESP32.",
            parent=self,
        ):
            return

        if self.client:
            self.disconnect()
        self.flash_button.configure(state=tk.DISABLED)
        self.status_var.set(f"Flashing {Path(binary).name} to {port}...")

        def worker() -> None:
            command = [
                sys.executable,
                "-m",
                "esptool",
                "--chip",
                "esp32s3",
                "--port",
                port,
                "--baud",
                "460800",
                "write-flash",
                "0x10000",
                binary,
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                output = (result.stdout or "") + (result.stderr or "")
                if result.returncode != 0:
                    raise RuntimeError(output.strip()[-3000:] or f"esptool exited with code {result.returncode}")
                self.after(0, lambda: self._flash_finished(port))
            except Exception as exc:
                self.after(0, lambda error=str(exc): self._flash_failed(error))

        threading.Thread(target=worker, name="firmware-flash", daemon=True).start()

    def _flash_finished(self, port: str) -> None:
        self.flash_button.configure(state=tk.NORMAL)
        self.status_var.set(f"Firmware flashed successfully on {port}. Reconnect after the port reappears.")
        self.after(1500, self.refresh_ports)
        messagebox.showinfo(
            "Flash complete",
            "AmazingHand SCS0009 firmware was flashed successfully.\n\n"
            "Reconnect the GUI, then assign IDs with exactly one servo connected.",
            parent=self,
        )

    def _flash_failed(self, error: str) -> None:
        self.flash_button.configure(state=tk.NORMAL)
        self.status_var.set("Firmware flash failed")
        messagebox.showerror(
            "Flash failed",
            f"{error}\n\nIf the board was not detected, hold BOOT, tap RESET, release BOOT, and try again.",
            parent=self,
        )

    def assign_id(self) -> None:
        if not self.client:
            return
        new_id = simpledialog.askinteger(
            "Assign SCS0009 ID",
            "Connect exactly one servo. Enter its AmazingHand ID (1-8):",
            minvalue=1,
            maxvalue=8,
            parent=self,
        )
        if new_id is None:
            return
        self.status_var.set(f"Scanning the bus and assigning ID {new_id}...")
        self.update_idletasks()
        try:
            old_id, reported_id, status = self.client.set_id(new_id)
            # SET_ID always disables torque in the ESP32 firmware. Keep the UI
            # state synchronized so the next ARM click really re-enables it.
            self.armed = False
            self.arm_button.configure(text="ARM TORQUE")
            description = SET_ID_STATUS.get(status, f"unknown status {status}")
            if status:
                raise RuntimeError(description)
            self.status_var.set(
                f"ID assignment successful: {old_id} -> {reported_id}. "
                f"To test it, click ARM TORQUE and move the ID {reported_id} slider slowly."
            )
            messagebox.showinfo(
                "ID assigned",
                f"Servo ID changed from {old_id} to {reported_id}.\n\n"
                f"To test this servo:\n"
                f"1. Leave this one servo connected.\n"
                f"2. Click ARM TORQUE.\n"
                f"3. Slowly move the ID {reported_id} slider.\n\n"
                "Disarm it before disconnecting or connecting another servo.",
            )
        except Exception as exc:
            self.armed = False
            self.arm_button.configure(text="ARM TORQUE")
            self.status_var.set(f"ID assignment failed: {exc}")
            messagebox.showerror("ID assignment failed", str(exc))

    def scan_ids(self) -> None:
        if not self.client:
            return
        try:
            mask = self.client.ping_all()
            found = [str(i + 1) for i in range(8) if mask & (1 << i)]
            missing = [str(i + 1) for i in range(8) if not mask & (1 << i)]
            self.status_var.set(f"Found IDs: {', '.join(found) or 'none'}; missing: {', '.join(missing) or 'none'}")
        except Exception as exc:
            messagebox.showerror("ID scan failed", str(exc))

    def apply_speed(self) -> None:
        if not self.client:
            return
        try:
            speed = self.client.set_speed(int(self.speed_var.get()))
            self.status_var.set(f"Motion speed set to {speed} (6 is fastest)")
        except Exception as exc:
            messagebox.showerror("Speed setting failed", str(exc))

    def calibrate_open_pose(self) -> None:
        if not self.client:
            return
        if not messagebox.askyesno(
            "Teach open/zero pose",
            "This will disable torque and save the CURRENT position of every responding servo as 0 degrees.\n\n"
            "Before continuing, support the hand and manually place every connected finger in its open, centered neutral pose. Continue?",
            parent=self,
        ):
            return
        try:
            mask, _first_raw, status = self.client.calibrate_zero(0)
            self.armed = False
            self.arm_button.configure(text="ARM TORQUE")
            if status:
                raise RuntimeError("No servos responded during calibration")
            calibrated = [str(i + 1) for i in range(8) if mask & (1 << i)]
            ids = ", ".join(calibrated)
            self.status_var.set(f"Saved open/zero calibration for IDs: {ids}. Torque remains disabled.")
            messagebox.showinfo(
                "Calibration saved",
                f"Saved the current pose as 0 degrees for IDs: {ids}.\n\n"
                "Keep the mechanism clear, click ARM TORQUE, then use Home or make small slider movements.",
                parent=self,
            )
        except Exception as exc:
            self.armed = False
            self.arm_button.configure(text="ARM TORQUE")
            messagebox.showerror("Calibration failed", str(exc), parent=self)

    def reset_calibration(self) -> None:
        if not self.client:
            return
        if not messagebox.askyesno(
            "Reset calibration",
            "Reset all eight zero positions to the factory midpoint (raw 511)? Torque will be disabled.",
            parent=self,
        ):
            return
        try:
            self.client.reset_calibration()
            self.armed = False
            self.arm_button.configure(text="ARM TORQUE")
            self.status_var.set("Calibration reset to raw midpoint 511; torque disabled")
        except Exception as exc:
            messagebox.showerror("Calibration reset failed", str(exc), parent=self)

    def toggle_arm(self) -> None:
        if not self.client:
            return
        try:
            if self.armed:
                self.client.disarm()
                self.armed = False
                self.arm_button.configure(text="ARM TORQUE")
                self.status_var.set("Torque disabled")
            else:
                if not messagebox.askyesno("Arm torque", "Is the hand clear of people and obstructions?"):
                    return
                self.client.arm()
                self.armed = True
                self.arm_button.configure(text="DISARM TORQUE")
                self.status_var.set("ARMED - slider commands are live")
                self._send_angles()
        except Exception as exc:
            messagebox.showerror("Torque command failed", str(exc))

    def _slider_changed(self, _value: str) -> None:
        if self.armed:
            self._send_angles()

    def _send_angles(self) -> None:
        if not self.client or not self.armed:
            return
        try:
            self.client.send_angles([variable.get() for variable in self.angle_vars])
        except Exception as exc:
            self.status_var.set(f"Motion command failed: {exc}")

    def open_targets(self) -> None:
        for variable in self.angle_vars:
            variable.set(0.0)
        if self.armed:
            self._send_angles()

    def on_close(self) -> None:
        self.disconnect()
        self.destroy()


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()

