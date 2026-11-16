"""Read and teach per-test logical servo poses without hardware dependencies."""

import json
import math
from pathlib import Path


STAGES = ("approach", "pinch", "release")


def validate_targets(targets):
    if not isinstance(targets, (list, tuple)) or len(targets) != 8:
        raise ValueError("A grasp pose needs eight servo targets")
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) or not -40 <= v <= 110 for v in targets):
        raise ValueError("Grasp targets must be finite degrees between -40 and 110")
    return tuple(targets)


def load_profile(path):
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    if profile.get("version") != 1 or profile.get("servo_ids") != list(range(1, 9)):
        raise ValueError("Unsupported grasp format or servo order")
    poses = profile.get("poses")
    if not isinstance(poses, dict) or set(poses) != set(STAGES):
        raise ValueError("Grasp needs approach, pinch, and release poses")
    for targets in poses.values():
        if targets is not None:
            validate_targets(targets)
    return profile


def save_pose(path, stage, targets):
    if stage not in STAGES:
        raise ValueError("Unknown grasp stage")
    profile = load_profile(path)
    profile["poses"][stage] = list(validate_targets(targets))
    destination = Path(path)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
