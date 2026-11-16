"""Signed thumb spread relative to a calibrated, camera-facing palm."""

import math


class ThumbAbduction:
    def __init__(self, gain=0.5, direction=1, smoothing=0.25, full_spread=25.0):
        self.gain = max(0.0, min(1.0, float(gain)))
        self.direction = -1 if direction < 0 else 1
        self.alpha = max(0.0, min(1.0, float(smoothing)))
        self.full_spread = float(full_spread)
        if not math.isfinite(self.full_spread) or self.full_spread <= 3:
            raise ValueError("Thumb side range must be finite and greater than 3")
        self._neutral = None
        self._previous = 0.0

    @staticmethod
    def _angle(keypoints):
        if len(keypoints) != 21:
            return None
        points = [(float(p.x), float(p.y)) for p in keypoints]
        if not all(math.isfinite(v) for p in points for v in p):
            return None
        across = tuple(points[5][j] - points[17][j] for j in (0, 1))
        forward = tuple(points[9][j] - points[0][j] for j in (0, 1))
        det = across[0] * forward[1] - across[1] * forward[0]
        lengths = math.hypot(*across) * math.hypot(*forward)
        if lengths < 1e-10 or abs(det) < 0.15 * lengths:
            return None
        # CMC -> MCP measures the thumb base rather than distal thumb curl.
        dx, dy = (points[2][j] - points[1][j] for j in (0, 1))
        lateral = (dx * forward[1] - dy * forward[0]) / det
        longitudinal = (across[0] * dy - across[1] * dx) / det
        if math.hypot(lateral, longitudinal) < 0.08:
            return None
        return math.degrees(math.atan2(lateral, longitudinal))

    def calibrate(self, keypoints):
        self._neutral = self._angle(keypoints)
        self._previous = 0.0
        return self._neutral is not None

    def retarget(self, keypoints):
        angle = self._angle(keypoints)
        target = 0.0
        if angle is not None and self._neutral is not None:
            delta = (angle - self._neutral + 180) % 360 - 180
            fraction = min(1.0, max(0.0, (abs(delta) - 3) / (self.full_spread - 3)))
            target = math.copysign(40 * self.gain * fraction, delta) * self.direction
        self._previous += self.alpha * (target - self._previous)
        return self._previous
