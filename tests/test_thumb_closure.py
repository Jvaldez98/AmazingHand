import math
from types import SimpleNamespace
import unittest

from thumb_closure import ThumbClosure
from teleop_mapping import map_aero_angles_to_amazing


def palm():
    points = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    for i, x, y in ((5, .5, 1), (9, 0, 1), (17, -.5, 1), (4, 1, .5)):
        points[i] = SimpleNamespace(x=x, y=y)
    return points


class ThumbClosureTests(unittest.TestCase):
    def test_inward_motion_closes_even_when_joint_angles_decrease(self):
        points = palm()
        tracker = ThumbClosure(smoothing=1)
        self.assertTrue(tracker.calibrate(points))
        targets = []
        for distance in (1, .8, .6, .4, .2, 0, -.2):
            points[4].x = distance
            closure = tracker.retarget(points)
            targets.append(map_aero_angles_to_amazing([0] * 16, thumb_closure=closure)[6])
        self.assertEqual(targets, sorted(targets))
        self.assertEqual(targets[-1], 110)
        self.assertEqual(targets[0], 0)

    def test_index_curl_does_not_change_thumb(self):
        points = palm()
        tracker = ThumbClosure(smoothing=1)
        tracker.calibrate(points)
        points[4].x = .6
        before = tracker.retarget(points)
        for i in (6, 7, 8):
            points[i].x, points[i].y = .1, .2
        self.assertEqual(tracker.retarget(points), before)

    def test_palm_transform_preserves_closure(self):
        points = palm()
        tracker = ThumbClosure(smoothing=1)
        tracker.calibrate(points)
        points[4].x = .6
        before = tracker.retarget(points)
        for p in points:
            x, y = p.x, p.y
            p.x = .3 + 2 * (x * math.cos(.7) - y * math.sin(.7))
            p.y = .8 + 3 * (x * math.sin(.7) + y * math.cos(.7))
        self.assertAlmostEqual(tracker.retarget(points), before)

    def test_invalid_and_uncalibrated_use_angle_fallback(self):
        tracker = ThumbClosure()
        self.assertIsNone(tracker.retarget(palm()))
        tracker.calibrate(palm())
        self.assertIsNone(tracker.retarget([]))
        points = palm()
        for p in points:
            p.x = 0
        self.assertFalse(tracker.calibrate(points))
        self.assertIsNone(tracker.retarget(palm()))


if __name__ == '__main__':
    unittest.main()
