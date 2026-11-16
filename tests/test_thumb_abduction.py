import math
import unittest
from types import SimpleNamespace

from thumb_abduction import ThumbAbduction
from teleop_mapping import MappingConfig, map_aero_angles_to_amazing


def palm(angle=40):
    p = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    for i, x in ((5, 0.5), (9, 0), (17, -0.5)):
        p[i] = SimpleNamespace(x=x, y=1.0)
    p[1] = SimpleNamespace(x=0.2, y=0.2)
    p[2] = SimpleNamespace(x=0.2 + 0.5 * math.sin(math.radians(angle)),
                           y=0.2 + 0.5 * math.cos(math.radians(angle)))
    return p


class ThumbAbductionTests(unittest.TestCase):
    def test_opposition_retains_side_at_full_closure_within_limits(self):
        cfg = MappingConfig(thumb_opposition=True)
        for side in (-40, -30, 0, 30, 40):
            targets = map_aero_angles_to_amazing([0] * 16, cfg, thumb_closure=1, thumb_side=side)
            self.assertEqual(targets[:6], (0,) * 6)
            pair = targets[-2:]
            self.assertTrue(all(-40 <= v <= 110 for v in pair))
            if side:
                self.assertNotEqual(*pair)
                self.assertEqual(pair[0] > pair[1], side < 0)
            else:
                self.assertEqual(pair, (110, 110))

    def test_calibration_signed_spread_gain_and_inversion(self):
        for direction in (1, -1):
            tracker = ThumbAbduction(gain=0.75, direction=direction, smoothing=1)
            self.assertEqual(tracker.retarget(palm()), 0)
            self.assertTrue(tracker.calibrate(palm()))
            self.assertEqual(tracker.retarget(palm()), 0)
            self.assertAlmostEqual(tracker.retarget(palm(65)), 30 * direction)
            self.assertAlmostEqual(tracker.retarget(palm(15)), -30 * direction)

    def test_palm_transform_preserves_angle(self):
        tracker = ThumbAbduction(smoothing=1)
        tracker.calibrate(palm())
        points = palm()
        for p in points:
            x, y = p.x, p.y
            p.x = 2 + 2 * (x * math.cos(0.6) - y * math.sin(0.6))
            p.y = 3 + 3 * (x * math.sin(0.6) + y * math.cos(0.6))
        self.assertAlmostEqual(tracker.retarget(points), 0)

    def test_invalid_tracking_returns_to_neutral(self):
        tracker = ThumbAbduction(smoothing=1)
        tracker.calibrate(palm())
        tracker.retarget(palm(65))
        self.assertEqual(tracker.retarget([]), 0)
        self.assertFalse(tracker.calibrate([]))

    def test_override_controls_only_thumb_and_preserves_closure(self):
        for side in (-30, 30):
            targets = map_aero_angles_to_amazing([0] * 16, thumb_side=side)
            self.assertEqual(targets[:6], (0,) * 6)
            self.assertNotEqual(targets[6], targets[7])
            closed = map_aero_angles_to_amazing([0] * 16, thumb_side=side, thumb_closure=1)
            self.assertEqual(closed[-2:], (110, 110))
