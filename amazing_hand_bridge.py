"""Thread-safe Waveshare/SCServo hardware bridge for AmazingHand."""

from __future__ import annotations

import math
import threading
from typing import Callable, Optional, Sequence

from teleop_mapping import SERVO_IDS, clamp


class AmazingHandBridge:
    """Own the rustypot controller and expose degree-based synchronized writes."""

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 1_000_000,
        speed: int = 3,
        mock: bool = False,
        verbose: bool = False,
        controller_factory: Optional[Callable[..., object]] = None,
    ) -> None:
        self.mock = bool(mock or not port)
        self.verbose = verbose
        self.controller = None
        self._lock = threading.RLock()
        self._last_targets: Optional[tuple[int, ...]] = None

        if self.mock:
            print("[AmazingHandBridge] MOCK mode: no servo commands will be sent.")
            return

        if controller_factory is None:
            try:
                from rustypot import Scs0009PyController
            except ImportError as exc:
                raise RuntimeError(
                    "rustypot is required for hardware mode. Install the teleop requirements first."
                ) from exc
            controller_factory = Scs0009PyController

        try:
            controller = controller_factory(
                serial_port=port,
                baudrate=int(baudrate),
                timeout=0.5,
            )
            with self._lock:
                self.controller = controller
                for servo_id in SERVO_IDS:
                    controller.write_torque_enable(servo_id, 1)
                    controller.write_goal_speed(servo_id, int(speed))
        except Exception:
            self.controller = None
            raise

        print(f"[AmazingHandBridge] Connected to AmazingHand on {port} at {baudrate} baud.")

    @staticmethod
    def _to_radians(servo_id: int, degrees: float) -> float:
        # The current AmazingHand GUI applies this inversion to even servo IDs.
        signed_degrees = -degrees if servo_id % 2 == 0 else degrees
        return math.radians(signed_degrees)

    def send_servo_degrees(self, targets: Sequence[float]) -> None:
        """Send targets corresponding to servo IDs 1..8 in one sync write."""

        if len(targets) != len(SERVO_IDS):
            raise ValueError(f"Expected 8 servo targets, got {len(targets)}")
        safe_targets = tuple(int(round(clamp(float(value), -40.0, 110.0))) for value in targets)

        if self.mock:
            if self.verbose and safe_targets != self._last_targets:
                print(f"[MOCK servo targets] {safe_targets}")
            self._last_targets = safe_targets
            return

        radians = [
            self._to_radians(servo_id, target)
            for servo_id, target in zip(SERVO_IDS, safe_targets)
        ]
        with self._lock:
            if self.controller is None:
                raise RuntimeError("AmazingHand controller is not connected")
            self.controller.sync_write_goal_position(list(SERVO_IDS), radians)
        self._last_targets = safe_targets

    def open_hand(self) -> None:
        self.send_servo_degrees((0,) * 8)

    def close_hand(self) -> None:
        self.send_servo_degrees((110,) * 8)

    def close(self) -> None:
        """Disable torque and release our controller reference."""

        if self.mock:
            return
        with self._lock:
            controller = self.controller
            if controller is None:
                return
            for servo_id in SERVO_IDS:
                try:
                    controller.write_torque_enable(servo_id, 0)
                except Exception:
                    pass
            self.controller = None
        print("[AmazingHandBridge] Disconnected; servo torque disabled.")

