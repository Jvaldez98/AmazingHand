import math
from types import SimpleNamespace
import unittest

from finger_abduction import FingerAbduction
from teleop_mapping import map_aero_angles_to_amazing


def palm():
    points = [SimpleNamespace(x=0.0, y=0.0) for _ in range(21)]
    for index, x in ((5, 0.5), (9, 0.0), (13, -0.25), (17, -0.5)):
        points[index] = SimpleNamespace(x=x, y=1.0)
        points[index + 1] = SimpleNamespace(x=x, y=1.5)
    return points


class FingerAbductionTests(unittest.TestCase):
    def test_requires_calibration_and_neutral_stays_zero(self):
        tracker = FingerAbduction(gain=1, smoothing=1)
        points = palm()
        self.assertEqual(tracker.retarget(points), (0, 0, 0))
        self.assertTrue(tracker.calibrate(points))
        self.assertEqual(tracker.retarget(points), (0, 0, 0))

    def test_spread_separates_only_requested_pair_and_can_invert(self):
        for direction in (1, -1):
            tracker = FingerAbduction(gain=0.25, directions=(direction, 1, 1), smoothing=1)
            points = palm()
            tracker.calibrate(points)
            points[6].x += 0.3
            sides = tracker.retarget(points)
            self.assertEqual(sides, (10 * direction, 0, 0))
            targets = map_aero_angles_to_amazing([0] * 16, finger_sides=sides)
            self.assertNotEqual(targets[0], targets[1])
            self.assertEqual(targets[2:], (0,) * 6)

    def test_palm_motion_does_not_create_spread(self):
        tracker = FingerAbduction(gain=1, smoothing=1)
        points = palm()
        tracker.calibrate(points)
        for p in points:
            x, y = p.x, p.y
            p.x = 0.3 + 2 * (x * math.cos(0.7) - y * math.sin(0.7))
            p.y = 0.8 + 3 * (x * math.sin(0.7) + y * math.cos(0.7))
        self.assertEqual(tracker.retarget(points), (0, 0, 0))

    def test_invalid_palm_and_curled_segment_do_not_request_spread(self):
        tracker = FingerAbduction(gain=1, smoothing=1)
        points = palm()
        tracker.calibrate(points)
        points[6].x += 0.3
        points[6].y = 1.0
        self.assertEqual(tracker.retarget(points), (0, 0, 0))
        for p in points:
            p.x = 0
        self.assertFalse(tracker.calibrate(points))
        self.assertEqual(tracker.retarget(points), (0, 0, 0))

    def test_full_curl_removes_side_motion(self):
        angles = [100, 55, 90, 90] + [90] * 12
        self.assertEqual(
            map_aero_angles_to_amazing(angles, finger_sides=(40, -40, 40)), (110,) * 8,
        )

    def test_independent_ranges_amplify_middle_and_ring_with_reversed_signs(self):
        tracker = FingerAbduction(
            gain=0.75, directions=(-1, -1, -1), smoothing=1,
            full_spread=(25, 12, 12),
        )
        points = palm()
        tracker.calibrate(points)
        for pip in (6, 10, 14):
            points[pip].x += 0.5 * math.tan(math.radians(12))
        sides = tracker.retarget(points)
        self.assertAlmostEqual(sides[0], -30 * 9 / 22)
        self.assertAlmostEqual(sides[1], -30)
        self.assertAlmostEqual(sides[2], -30)
        targets = map_aero_angles_to_amazing([0] * 16, finger_sides=sides)
        self.assertGreater(targets[2], targets[3])
        self.assertGreater(targets[4], targets[5])

    def test_side_ranges_reject_invalid_values(self):
        for ranges in ((25, 3, 12), (25, float('nan'), 12), (25, 12)):
            with self.assertRaises(ValueError):
                FingerAbduction(full_spread=ranges)


if __name__ == "__main__":
    unittest.main()
