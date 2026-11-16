import math
import unittest

from amazing_hand_bridge import AmazingHandBridge


class FakeController:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.torque = []
        self.speeds = []
        self.sync_writes = []

    def write_torque_enable(self, servo_id, enabled):
        self.torque.append((servo_id, enabled))

    def write_goal_speed(self, servo_id, speed):
        self.speeds.append((servo_id, speed))

    def sync_write_goal_position(self, servo_ids, radians):
        self.sync_writes.append((servo_ids, radians))


class AmazingHandBridgeTests(unittest.TestCase):
    def test_even_servo_angles_are_inverted(self):
        bridge = AmazingHandBridge(port="TEST", controller_factory=FakeController)
        fake = bridge.controller
        bridge.send_servo_degrees([10] * 8)
        ids, radians = fake.sync_writes[-1]
        self.assertEqual(ids, list(range(1, 9)))
        for servo_id, value in zip(ids, radians):
            expected = math.radians(-10 if servo_id % 2 == 0 else 10)
            self.assertAlmostEqual(value, expected)

    def test_connect_and_close_manage_all_torque(self):
        bridge = AmazingHandBridge(port="TEST", controller_factory=FakeController)
        fake = bridge.controller
        self.assertEqual(fake.torque, [(servo_id, 1) for servo_id in range(1, 9)])
        bridge.close()
        self.assertEqual(fake.torque[-8:], [(servo_id, 0) for servo_id in range(1, 9)])

    def test_mock_mode_accepts_targets_without_controller(self):
        bridge = AmazingHandBridge(mock=True)
        bridge.send_servo_degrees([0] * 8)
        self.assertIsNone(bridge.controller)


if __name__ == "__main__":
    unittest.main()
