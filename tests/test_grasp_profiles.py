import json
from pathlib import Path
import tempfile
import unittest

from grasp_profiles import load_profile, save_pose, validate_targets


class GraspProfileTests(unittest.TestCase):
    def test_teaching_preserves_other_stages_and_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'card.json'
            original = load_profile(Path(__file__).resolve().parents[1] / 'grasps/card.json')
            path.write_text(json.dumps(original), encoding='utf-8')
            save_pose(path, 'pinch', [20, 21, 0, 0, 0, 0, 30, 31])
            saved = load_profile(path)
            self.assertEqual(saved['poses']['pinch'], [20, 21, 0, 0, 0, 0, 30, 31])
            self.assertEqual(saved['poses']['approach'], original['poses']['approach'])
            self.assertEqual(saved['notes'], original['notes'])
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                save_pose(path, 'pinch', [111] * 8)
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_targets_are_rejected(self):
        for values in ([0] * 7, [float('nan')] * 8, [True] * 8, [-41] * 8):
            with self.assertRaises(ValueError):
                validate_targets(values)

    def test_templates_load(self):
        for name in ('card', 'string'):
            profile = load_profile(Path(__file__).resolve().parents[1] / f'grasps/{name}.json')
            self.assertTrue(all(validate_targets(p) for p in profile['poses'].values()))
