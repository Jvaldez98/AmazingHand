"""AmazingHand teleoperation bridge for the TetherIA/Chestnut ESP32 PCB."""

from __future__ import annotations

import threading
from typing import Optional, Sequence

from amazinghand_tether_gui import HOST_BAUD, TetherAmazingHand
from teleop_mapping import SERVO_IDS, clamp


class TetherEsp32Bridge:
    """Expose the same degree-based interface as the direct Waveshare bridge."""

    def __init__(
        self,
        port: str,
        baudrate: int = HOST_BAUD,
        verbose: bool = False,
        reverse_motors: bool = False,
    ) -> None:
        if not port:
            raise ValueError("An ESP32 COM port is required")
        self.client = TetherAmazingHand(port, baudrate=baudrate)
        self.verbose = verbose
        self.reverse_motors = bool(reverse_motors)
        self._lock = threading.RLock()
        self._armed = False
        self._last_targets: Optional[tuple[int, ...]] = None
        print(f"[TetherEsp32Bridge] Connected to {port} at {baudrate} baud; torque remains disabled.")

    def send_servo_degrees(self, targets: Sequence[float]) -> None:
        if len(targets) != len(SERVO_IDS):
            raise ValueError(f"Expected 8 servo targets, got {len(targets)}")
        safe_targets = tuple(int(round(clamp(float(value), -40.0, 110.0))) for value in targets)
        global_direction = -1 if self.reverse_motors else 1
        physical_targets = tuple(
            target * (-1 if servo_id % 2 == 0 else 1) * global_direction
            for servo_id, target in zip(SERVO_IDS, safe_targets)
        )
        with self._lock:
            if not self._armed:
                self.client.arm()
                self._armed = True
            self.client.send_angles(physical_targets)
        if self.verbose and safe_targets != self._last_targets:
            print(f"[ESP32 servo targets] logical={safe_targets} physical={physical_targets}")
        self._last_targets = safe_targets

    def open_hand(self) -> None:
        self.send_servo_degrees((0,) * 8)

    def close_hand(self) -> None:
        self.send_servo_degrees((110,) * 8)

    def close(self) -> None:
        with self._lock:
            client, self.client = self.client, None
            if client is None:
                return
            client.close()
            self._armed = False
        print("[TetherEsp32Bridge] Disconnected; servo torque disabled.")

