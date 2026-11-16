"""Thumb closure from image palm coordinates, independent of finger tips."""

import math


class ThumbClosure:
    def __init__(self, smoothing=0.25):
        self.alpha = max(0.0, min(1.0, float(smoothing)))
        self._open = None
        self._previous = 0.0

    @staticmethod
    def _distance(keypoints):
        if len(keypoints) != 21:
            return None
        points = [(float(p.x), float(p.y)) for p in keypoints]
        if not all(math.isfinite(v) for p in points for v in p):
            return None
        wrist, index, middle, pinky = (points[i] for i in (0, 5, 9, 17))
        across = (index[0] - pinky[0], index[1] - pinky[1])
        forward = (middle[0] - wrist[0], middle[1] - wrist[1])
        det = across[0] * forward[1] - across[1] * forward[0]
        lengths = math.hypot(*across) * math.hypot(*forward)
        if lengths < 1e-10 or abs(det) < 0.15 * lengths:
            return None
        center = tuple((wrist[j] + middle[j]) / 2 for j in (0, 1))
        dx, dy = (points[4][j] - center[j] for j in (0, 1))
        lateral = (dx * forward[1] - dy * forward[0]) / det
        longitudinal = (across[0] * dy - across[1] * dx) / det
        return math.hypot(lateral, longitudinal)

    def calibrate(self, keypoints):
        distance = self._distance(keypoints)
        self._open = distance if distance is not None and distance > 0.1 else None
        self._previous = 0.0
        return self._open is not None

    def retarget(self, keypoints):
        distance = self._distance(keypoints)
        if self._open is None or distance is None:
            return None
        # Reach full closure at 35% of the open distance, with a small rest
        # deadband. The plateau prevents reopening when passing palm center.
        fraction = max(0.0, min(1.0, (0.95 - distance / self._open) / 0.60))
        self._previous += self.alpha * (fraction - self._previous)
        return self._previous
