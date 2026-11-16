"""Calibrated finger spread from image landmarks, independent of MediaPipe.

Use a 2D palm basis instead of mixing image coordinates with estimated/metric
depth. This is intended for a palm facing the camera; edge-on poses are rejected.
"""

import math


class FingerAbduction:
    def __init__(self, gain=0.0, directions=(1, 1, 1), smoothing=0.25,
                 full_spread=(25.0, 25.0, 25.0)):
        self.gain = max(0.0, min(1.0, float(gain)))
        self.directions = tuple(directions)
        if len(self.directions) != 3:
            raise ValueError("Expected three finger directions")
        self.full_spread = tuple(float(value) for value in full_spread)
        if len(self.full_spread) != 3 or any(
            not math.isfinite(value) or value <= 3.0 for value in self.full_spread
        ):
            raise ValueError("Each finger side range must be finite and greater than 3")
        self.alpha = max(0.0, min(1.0, float(smoothing)))
        self._neutral = None
        self._previous = (0.0, 0.0, 0.0)

    @staticmethod
    def _angles(keypoints):
        if len(keypoints) != 21:
            return None
        points = [(float(p.x), float(p.y)) for p in keypoints]
        if not all(math.isfinite(v) for p in points for v in p):
            return None
        # Across points toward the thumb for either hand. Forward points from
        # the wrist toward the middle knuckle. Solving in this basis removes
        # image aspect ratio, translation, scale, and in-plane rotation.
        across = tuple(a - b for a, b in zip(points[5], points[17]))
        forward = tuple(a - b for a, b in zip(points[9], points[0]))
        det = across[0] * forward[1] - across[1] * forward[0]
        lengths = math.hypot(*across) * math.hypot(*forward)
        if lengths < 1e-10 or abs(det) < 0.15 * lengths:
            return None
        angles = []
        for mcp, pip in ((5, 6), (9, 10), (13, 14)):
            dx = points[pip][0] - points[mcp][0]
            dy = points[pip][1] - points[mcp][1]
            lateral = (dx * forward[1] - dy * forward[0]) / det
            longitudinal = (across[0] * dy - across[1] * dx) / det
            # A curled/foreshortened proximal segment has unreliable spread.
            if longitudinal <= 0.08:
                angles.append(None)
            else:
                angles.append(math.degrees(math.atan2(lateral, longitudinal)))
        return angles

    def calibrate(self, keypoints):
        angles = self._angles(keypoints)
        if angles is None or any(a is None for a in angles):
            return False
        self._neutral = angles
        self._previous = (0.0, 0.0, 0.0)
        return True

    def retarget(self, keypoints):
        angles = self._angles(keypoints)
        targets = [0.0, 0.0, 0.0]
        if angles is not None and self._neutral is not None:
            for i, (angle, neutral) in enumerate(zip(angles, self._neutral)):
                if angle is None:
                    continue
                delta = angle - neutral
                # Per-finger sensitivity in palm coordinates, with a three-degree
                # deadband. Output retains the existing +/-40 side scale.
                fraction = min(1.0, max(0.0, (abs(delta) - 3.0) / (self.full_spread[i] - 3.0)))
                direction = -1 if self.directions[i] < 0 else 1
                targets[i] = math.copysign(40.0 * self.gain * fraction, delta) * direction
        self._previous = tuple(
            self.alpha * target + (1.0 - self.alpha) * previous
            for target, previous in zip(targets, self._previous)
        )
        return self._previous
