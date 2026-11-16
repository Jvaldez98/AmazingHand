"""Safe webcam teleoperation entry point for AmazingHand.

The program starts DISARMED. Press SPACE after a tracked hand is visible to
allow commands. Losing tracking opens the hand and disarms teleoperation by
default.
"""

from __future__ import annotations

import argparse
import threading
import time
from typing import Optional

import cv2
import numpy as np

from amazing_hand_bridge import AmazingHandBridge
from finger_abduction import FingerAbduction
from teleop_mapping import MappingConfig, map_aero_angles_to_amazing
from thumb_closure import ThumbClosure
from thumb_abduction import ThumbAbduction
from grasp_profiles import STAGES, load_profile, save_pose
from teleop_vision import HandMocap, MediaPipeMocap, MediaPipeRetargeting, RetargetingConfig


class AmazingHandTeleop:
    WARMUP_FRAMES = 5

    def __init__(
        self,
        bridge: object,
        camera_index: int = 0,
        hand_side: str = "right",
        camera_fps: float = 30.0,
        control_hz: float = 15.0,
        smoothing_alpha: float = 0.25,
        lost_timeout: float = 0.5,
        loss_action: str = "open",
        force_webcam: bool = False,
        mapping_config: Optional[MappingConfig] = None,
        finger_side_gain: float = 0.0,
        finger_side_directions: tuple[int, int, int] = (1, 1, 1),
        finger_side_ranges: tuple[float, float, float] = (25.0, 25.0, 25.0),
        grasp_file: Optional[str] = None,
        thumb_side_range: float = 25.0,
    ) -> None:
        self.bridge = bridge
        self.grasp_file = grasp_file
        self._grasp_stage = 0
        self._grasp_targets = None
        self.control_hz = max(1.0, float(control_hz))
        self.lost_timeout = max(0.1, float(lost_timeout))
        self.loss_action = loss_action
        self.mapping_config = mapping_config or MappingConfig()
        self.thumb_closure = ThumbClosure(smoothing=smoothing_alpha)
        self.thumb_abduction = ThumbAbduction(
            gain=self.mapping_config.thumb_side_gain,
            direction=self.mapping_config.thumb_side_direction,
            smoothing=smoothing_alpha, full_spread=thumb_side_range,
        )
        self.finger_abduction = FingerAbduction(
            gain=finger_side_gain, directions=finger_side_directions, smoothing=smoothing_alpha,
            full_spread=finger_side_ranges,
        )

        self.retargeting = MediaPipeRetargeting(
            config=RetargetingConfig(),
            smoothing_alpha=smoothing_alpha,
        )
        self.mocap = MediaPipeMocap(
            camera_index=camera_index,
            target_fps=camera_fps,
            hand_side=hand_side,
            on_mocap=self._on_mocap,
            on_frame=self._on_frame,
            show_window=False,
            force_webcam=force_webcam,
        )

        self._lock = threading.Lock()
        self._running = False
        self._armed = False
        self._armed_at = 0.0
        self._last_seen = 0.0
        self._stable_frames = 0
        self._latest_mocap: Optional[HandMocap] = None
        self._latest_targets: Optional[tuple[int, ...]] = None
        self._latest_sides = (0.0, 0.0, 0.0)
        self._latest_thumb_side = 0.0
        self._calibrate_next = False
        self._manual_action: Optional[str] = None
        self._status = "DISARMED - show your hand, calibrate, then press SPACE"

    def _on_mocap(self, mocap: HandMocap) -> None:
        if self._calibrate_next:
            self.retargeting.calibrate(mocap)
            side_calibrated = self.finger_abduction.calibrate(mocap.keypoints)
            thumb_calibrated = self.thumb_closure.calibrate(mocap.keypoints)
            thumb_side_calibrated = self.thumb_abduction.calibrate(mocap.keypoints)
            self._calibrate_next = False
            with self._lock:
                self._stable_frames = 0
                self._status = (
                    "CALIBRATED - hold steady for warmup" if side_calibrated and thumb_calibrated and thumb_side_calibrated
                    else "Calibration failed - open thumb, face palm to camera and press c again"
                )

        angles = self.retargeting.retarget(mocap)
        sides = self.finger_abduction.retarget(mocap.keypoints)
        thumb_side = self.thumb_abduction.retarget(mocap.keypoints)
        targets = map_aero_angles_to_amazing(
            angles, self.mapping_config, sides,
            thumb_closure=self.thumb_closure.retarget(mocap.keypoints),
            thumb_side=thumb_side,
        )
        with self._lock:
            self._latest_mocap = mocap
            self._latest_targets = targets
            self._latest_sides = sides
            self._latest_thumb_side = thumb_side
            self._last_seen = time.monotonic()
            self._stable_frames += 1

    def _tracking_age(self, now: Optional[float] = None) -> Optional[float]:
        current = time.monotonic() if now is None else now
        with self._lock:
            last_seen = self._last_seen
        return current - last_seen if last_seen else None

    def _toggle_armed(self) -> None:
        with self._lock:
            if self._armed:
                self._armed = False
                self._status = "DISARMED"
                return
            self._armed = True
            self._armed_at = time.monotonic()
            self._stable_frames = 0
            self._status = "ARMING - waiting for stable tracking"

    def _queue_manual_action(self, action: str) -> None:
        with self._lock:
            self._armed = False
            self._manual_action = action
            self._status = f"DISARMED - queued {action.upper()} command"

    def _control_loop(self) -> None:
        interval = 1.0 / self.control_hz
        while self._running:
            started = time.monotonic()
            action = None
            targets = None

            with self._lock:
                if self._manual_action:
                    action = self._manual_action
                    if action == "grasp":
                        targets = self._grasp_targets
                    self._manual_action = None
                elif self._armed:
                    reference_time = self._last_seen or self._armed_at
                    tracking_age = started - reference_time
                    if tracking_age > self.lost_timeout:
                        self._armed = False
                        action = self.loss_action
                        self._status = "FAILSAFE - tracking lost; teleop DISARMED"
                    elif self._stable_frames >= self.WARMUP_FRAMES:
                        targets = self._latest_targets
                        self._status = "ARMED - LIVE CONTROL"

            try:
                if action == "open":
                    self.bridge.open_hand()
                elif action == "grasp":
                    self.bridge.send_servo_degrees(targets)
                elif action == "close":
                    self.bridge.close_hand()
                elif targets is not None:
                    self.bridge.send_servo_degrees(targets)
            except Exception as exc:
                with self._lock:
                    self._armed = False
                    self._status = f"HARDWARE ERROR - {exc}"
                print(f"[Teleop] Hardware error: {exc}")

            remaining = interval - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)

    def _on_frame(self, frame: np.ndarray) -> None:
        now = time.monotonic()
        age = self._tracking_age(now)
        with self._lock:
            armed = self._armed
            stable = self._stable_frames
            status = self._status
            targets = self._latest_targets
            sides = self._latest_sides
            thumb_side = self._latest_thumb_side

        tracking = age is not None and age <= self.lost_timeout
        color = (0, 220, 0) if armed and tracking else (0, 180, 255)
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 112), (20, 20, 20), -1)
        cv2.putText(frame, "AmazingHand Webcam Teleop", (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 220, 0), 2)
        cv2.putText(frame, status[:78], (12, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        track_text = f"tracking={'YES' if tracking else 'NO'}  warmup={stable}/{self.WARMUP_FRAMES}"
        cv2.putText(frame, track_text, (12, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (210, 210, 210), 1)
        cv2.putText(frame, "SPACE=arm/disarm  c=calibrate(open palm)  o=open  f=close  q=quit", (12, 96), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)
        if self.grasp_file:
            cv2.putText(frame, f"Grasp: {STAGES[self._grasp_stage]}  1/2/3=stage s=save p=apply(disarmed)", (12, 218), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 220, 0), 1)

        if targets:
            labels = ("PTR", "MID", "RNG", "THM")
            y = 128
            for index, label in enumerate(labels):
                pair = targets[index * 2:index * 2 + 2]
                side_text = (f"  side={sides[index]:+.1f}" if index < 3 else
                             f"  side={thumb_side:+.1f} gain={self.thumb_abduction.gain:.2f}")
                cv2.putText(frame, f"{label}: {pair[0]:>4} {pair[1]:>4}{side_text}", (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 255, 150), 1)
                y += 19

        cv2.imshow("AmazingHand - Webcam Teleop", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            self.mocap.stop()
        elif key == ord(" "):
            self._toggle_armed()
        elif key == ord("c"):
            self._calibrate_next = True
            with self._lock:
                self._status = "CALIBRATION ARMED - hold an open, flat palm"
        elif key == ord("o"):
            self._queue_manual_action("open")
        elif key == ord("f"):
            self._queue_manual_action("close")
        elif self.grasp_file and key in (ord("1"), ord("2"), ord("3")):
            self._grasp_stage = key - ord("1")
        elif self.grasp_file and key in (ord("s"), ord("p")):
            stage = STAGES[self._grasp_stage]
            try:
                if key == ord("s"):
                    with self._lock:
                        fresh = self._last_seen and time.monotonic() - self._last_seen <= self.lost_timeout
                        snapshot = self._latest_targets
                        ready = self._stable_frames >= self.WARMUP_FRAMES
                    if not fresh or not ready or snapshot is None:
                        raise ValueError("Hold a tracked hand steady before saving")
                    save_pose(self.grasp_file, stage, snapshot)
                    message = f"Saved {stage} to {self.grasp_file}"
                else:
                    pose = load_profile(self.grasp_file)["poses"][stage]
                    if pose is None:
                        raise ValueError(f"Teach {stage} with s first")
                    with self._lock:
                        if self._armed:
                            raise ValueError("Disarm with SPACE before applying a saved pose")
                        self._grasp_targets = tuple(pose)
                        self._manual_action = "grasp"
                    message = f"Queued saved {stage}; webcam control stays disarmed"
                with self._lock:
                    self._status = message
                print(f"[Grasp] {message}")
            except (OSError, ValueError, TypeError) as exc:
                with self._lock:
                    self._status = f"Grasp: {exc}"
                print(f"[Grasp] {exc}")

    def run(self) -> None:
        self._running = True
        control_thread = threading.Thread(target=self._control_loop, name="amazing-hand-control", daemon=True)
        control_thread.start()
        print("[Teleop] Started DISARMED. Press SPACE in the camera window to arm.")
        try:
            self.mocap.start()
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            control_thread.join(timeout=2.0)
            cv2.destroyAllWindows()
            self.bridge.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Webcam teleoperation for the four-finger AmazingHand")
    parser.add_argument("--port", help="Hardware serial port, for example COM3. Omit for mock mode.")
    parser.add_argument(
        "--transport",
        choices=("waveshare", "tether"),
        default="waveshare",
        help="Direct Waveshare bus adapter or TetherIA/Chestnut ESP32 PCB",
    )
    parser.add_argument("--baudrate", type=int, help="Defaults to 1000000 for Waveshare or 921600 for Tether")
    parser.add_argument("--speed", type=int, default=3, help="SCServo goal speed (existing GUI range: 1-6)")
    parser.add_argument("--mock", action="store_true", help="Never connect to or command hardware")
    parser.add_argument("--verbose", action="store_true", help="Print changed target commands in mock mode")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--hand", choices=("right", "left"), default="right")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--control-hz", type=float, default=15.0)
    parser.add_argument("--smoothing", type=float, default=0.25)
    parser.add_argument("--lost-timeout", type=float, default=0.5)
    parser.add_argument("--loss-action", choices=("open", "hold"), default="open")
    parser.add_argument("--force-webcam", action="store_true")
    parser.add_argument("--grasp-file", help="Per-test JSON profile; 1/2/3 select stage, s saves, p applies")
    parser.add_argument("--thumb-side-gain", type=float, default=0.5,
                        help="Thumb abduction strength (default: 0.5); use 0 to disable")
    parser.add_argument("--invert-thumb-side", action="store_true",
                        help="Reverse thumb abduction direction")
    parser.add_argument("--thumb-side-range", type=float, default=25.0,
                        help="Thumb angle change for full spread (default: 25 degrees, must be >3)")
    parser.add_argument("--thumb-opposition", action="store_true",
                        help="Preserve thumb sideways differential while curled; reduces common flexion to keep servo limits")
    parser.add_argument(
        "--finger-side-gain", type=float, default=0.0,
        help="Pointer/middle/ring spread strength, 0 to 1; start at 0.25 and calibrate with c",
    )
    parser.add_argument(
        "--finger-side-directions", type=int, nargs=3, choices=(-1, 1), default=(1, 1, 1),
        metavar=("PTR", "MID", "RNG"), help="Sideways motor directions for pointer, middle, ring",
    )
    parser.add_argument(
        "--finger-side-ranges", type=float, nargs=3, default=(25.0, 25.0, 25.0),
        metavar=("PTR", "MID", "RNG"),
        help="Tracked palm-coordinate angles for full spread; lower means more sensitive, each >3",
    )
    parser.add_argument(
        "--reverse-motors",
        action="store_true",
        help="Reverse all AmazingHand servo-pair motion if the mechanism moves in the wrong direction",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.grasp_file:
        load_profile(args.grasp_file)
    mapping = MappingConfig(
        thumb_side_gain=max(0.0, args.thumb_side_gain),
        thumb_side_direction=-1 if args.invert_thumb_side else 1,
        thumb_opposition=args.thumb_opposition,
    )
    if args.transport == "tether" and not args.mock and args.port:
        from tetheria_esp32_bridge import TetherEsp32Bridge

        bridge = TetherEsp32Bridge(
            port=args.port,
            baudrate=args.baudrate or 921_600,
            verbose=args.verbose,
            reverse_motors=args.reverse_motors,
        )
    else:
        bridge = AmazingHandBridge(
            port=args.port,
            baudrate=args.baudrate or 1_000_000,
            speed=args.speed,
            mock=args.mock,
            verbose=args.verbose,
        )
    teleop = AmazingHandTeleop(
        bridge=bridge,
        camera_index=args.camera,
        hand_side=args.hand,
        camera_fps=args.fps,
        control_hz=args.control_hz,
        smoothing_alpha=args.smoothing,
        lost_timeout=args.lost_timeout,
        loss_action=args.loss_action,
        force_webcam=args.force_webcam,
        mapping_config=mapping,
        thumb_side_range=args.thumb_side_range,
        finger_side_gain=args.finger_side_gain,
        finger_side_directions=tuple(args.finger_side_directions),
        finger_side_ranges=tuple(args.finger_side_ranges),
        grasp_file=args.grasp_file,
    )
    teleop.run()


if __name__ == "__main__":
    main()

