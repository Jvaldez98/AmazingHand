import unittest

from teleop_mapping import MappingConfig, compute_auto_pair, map_aero_angles_to_amazing


class TeleopMappingTests(unittest.TestCase):
    def test_open_hand_maps_to_zero(self):
        self.assertEqual(map_aero_angles_to_amazing([0.0] * 16), (0,) * 8)

    def test_closed_tracked_fingers_map_to_full_close(self):
        angles = [100.0, 55.0, 90.0, 90.0] + [90.0] * 12
        self.assertEqual(map_aero_angles_to_amazing(angles), (110,) * 8)

    def test_pinky_is_ignored(self):
        angles = [0.0] * 16
        angles[13:16] = [90.0, 90.0, 90.0]
        self.assertEqual(map_aero_angles_to_amazing(angles), (0,) * 8)

    def test_index_only_controls_pointer_pair(self):
        angles = [0.0] * 16
        angles[4:7] = [90.0, 90.0, 90.0]
        self.assertEqual(map_aero_angles_to_amazing(angles), (110, 110, 0, 0, 0, 0, 0, 0))

    def test_thumb_side_is_disabled_by_default(self):
        angles = [100.0] + [0.0] * 15
        self.assertEqual(map_aero_angles_to_amazing(angles), (0,) * 8)

    def test_pair_output_is_clamped(self):
        cfg = MappingConfig()
        for pair in (compute_auto_pair(0, -40, cfg), compute_auto_pair(0, 40, cfg)):
            self.assertTrue(all(-40 <= value <= 110 for value in pair))

    def test_enabled_thumb_abduction_and_direction(self):
        angles = [100.0] + [0.0] * 15
        normal = map_aero_angles_to_amazing(angles, MappingConfig(thumb_side_gain=0.5))
        reversed_side = map_aero_angles_to_amazing(
            angles, MappingConfig(thumb_side_gain=0.5, thumb_side_direction=-1),
        )
        self.assertEqual(normal, (0, 0, 0, 0, 0, 0, -20, 12))
        self.assertEqual(reversed_side[-2:], (12, -20))

    def test_thumb_abduction_preserves_full_closure(self):
        targets = map_aero_angles_to_amazing(
            [100.0] + [0.0] * 15, MappingConfig(thumb_side_gain=0.5), thumb_closure=1.0,
        )
        self.assertEqual(targets[-2:], (110, 110))

    def test_wrong_input_length_is_rejected(self):
        with self.assertRaises(ValueError):
            map_aero_angles_to_amazing([0.0] * 15)


if __name__ == "__main__":
    unittest.main()

