"""Pure angle mapping for AmazingHand webcam teleoperation.

The camera retargeter produces the 16-angle TetherIA/Aero convention.  The
AmazingHand has four fingers and two bus servos per finger, so this module
collapses each tracked finger into a single flexion value and expands that
value into the corresponding servo pair.

This module intentionally has no third-party dependencies so the mapping can
be unit-tested before a camera or robot is connected.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence, Tuple


SERVO_IDS: Tuple[int, ...] = tuple(range(1, 9))


@dataclass(frozen=True)
class MappingConfig:
    """Limits and optional thumb-side mapping for AmazingHand."""

    servo_min: float = -40.0
    servo_max: float = 110.0
    base_min: float = 0.0
    base_max: float = 110.0
    side_min: float = -40.0
    side_max: float = 40.0
    thumb_side_gain: float = 0.0
    thumb_side_direction: int = 1
    thumb_opposition: bool = False


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _safe_number(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def _weighted_flexion(
    angles: Sequence[float],
    maxima: Sequence[float],
    weights: Sequence[float],
) -> float:
    """Return a normalized [0, 1] flexion from several tracked joints."""

    total_weight = sum(weights)
    if total_weight <= 0:
        return 0.0
    normalized = (
        clamp(_safe_number(angle) / maximum, 0.0, 1.0) * weight
        for angle, maximum, weight in zip(angles, maxima, weights)
    )
    return clamp(sum(normalized) / total_weight, 0.0, 1.0)


def compute_auto_pair(
    base_position: float,
    side_offset: float,
    config: MappingConfig,
) -> Tuple[int, int]:
    """Convert AmazingHand base/side controls into a safe servo pair.

    The interpolation matches the behavior of the existing GUI.  At zero side
    offset both servos receive the same flexion target.
    """

    base = clamp(base_position, config.base_min, config.base_max)
    side = clamp(side_offset, config.side_min, config.side_max)
    span = config.base_max - config.base_min
    t = (base - config.base_min) / span if span else 0.0

    if side < 0:
        side_span = abs(config.side_min)
        u = abs(side) / side_span if side_span else 0.0
        left_open = (25.0, -40.0)
        left_closed = (110.0, 110.0)
        target = tuple(
            opened + t * (closed - opened)
            for opened, closed in zip(left_open, left_closed)
        )
    elif side > 0:
        side_span = config.side_max
        u = side / side_span if side_span else 0.0
        right_open = (-40.0, 25.0)
        right_closed = (110.0, 110.0)
        target = tuple(
            opened + t * (closed - opened)
            for opened, closed in zip(right_open, right_closed)
        )
    else:
        u = 0.0
        target = (base, base)

    pos1 = base + u * (target[0] - base)
    pos2 = base + u * (target[1] - base)
    return (
        int(round(clamp(pos1, config.servo_min, config.servo_max))),
        int(round(clamp(pos2, config.servo_min, config.servo_max))),
    )


def map_aero_angles_to_amazing(
    angles: Iterable[float],
    config: MappingConfig | None = None,
    finger_sides: Sequence[float] = (0.0, 0.0, 0.0),
    thumb_closure: float | None = None,
    thumb_side: float | None = None,
) -> Tuple[int, ...]:
    """Map 16 calibrated Aero joint angles to servo IDs 1 through 8.

    Input order is thumb(4), index(3), middle(3), ring(3), pinky(3).
    AmazingHand output order is pointer, middle, ring, thumb, with two servo
    targets for each finger.  Pinky tracking is intentionally ignored.
    """

    values = tuple(_safe_number(value) for value in angles)
    if len(values) != 16:
        raise ValueError(f"Expected 16 tracked joint angles, got {len(values)}")

    cfg = config or MappingConfig()
    if len(finger_sides) != 3:
        raise ValueError("Expected three side offsets: pointer, middle, ring")

    pointer = _weighted_flexion(values[4:7], (90.0, 90.0, 90.0), (0.25, 0.45, 0.30))
    middle = _weighted_flexion(values[7:10], (90.0, 90.0, 90.0), (0.25, 0.45, 0.30))
    ring = _weighted_flexion(values[10:13], (90.0, 90.0, 90.0), (0.25, 0.45, 0.30))
    thumb = _weighted_flexion(values[1:4], (55.0, 90.0, 90.0), (0.25, 0.35, 0.40))
    if thumb_closure is not None:
        thumb = clamp(_safe_number(thumb_closure), 0.0, 1.0)

    def to_base(fraction: float) -> float:
        return cfg.base_min + fraction * (cfg.base_max - cfg.base_min)

    thumb_abduction = clamp(values[0] / 100.0, 0.0, 1.0)
    direction = -1 if cfg.thumb_side_direction < 0 else 1
    thumb_side = clamp(_safe_number(thumb_side), cfg.side_min, cfg.side_max) if thumb_side is not None else clamp(
        thumb_abduction * cfg.side_max * cfg.thumb_side_gain * direction,
        cfg.side_min,
        cfg.side_max,
    )

    pointer_pair = compute_auto_pair(to_base(pointer), _safe_number(finger_sides[0]), cfg)
    middle_pair = compute_auto_pair(to_base(middle), _safe_number(finger_sides[1]), cfg)
    ring_pair = compute_auto_pair(to_base(ring), _safe_number(finger_sides[2]), cfg)
    if cfg.thumb_opposition:
        # Keep differential travel available when flexed. The ordinary finger
        # mixer converges to (110, 110), removing all side motion at closure.
        magnitude = abs(thumb_side)
        side_span = abs(cfg.side_min) if thumb_side < 0 else cfg.side_max
        fraction = magnitude / side_span if side_span else 0.0
        offsets = (25.0 * fraction, -40.0 * fraction) if thumb_side < 0 else (-40.0 * fraction, 25.0 * fraction)
        base = clamp(to_base(thumb), cfg.servo_min - min(offsets), cfg.servo_max - max(offsets))
        thumb_pair = tuple(int(round(clamp(base + offset, cfg.servo_min, cfg.servo_max))) for offset in offsets)
    else:
        thumb_pair = compute_auto_pair(to_base(thumb), thumb_side, cfg)
    return pointer_pair + middle_pair + ring_pair + thumb_pair

