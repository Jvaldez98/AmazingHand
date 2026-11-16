"""Expose only the reusable vision modules from the TetherIA reference repo.

The linked repository also imports optional grasp/LLM packages from its package
initializer.  Extending this package path lets AmazingHand reuse only the
MediaPipe capture and retargeting modules without requiring those extras.
"""

from pathlib import Path


_REFERENCE_DIR = Path(__file__).resolve().parent.parent / "tetheria_reference"
if not _REFERENCE_DIR.is_dir():
    raise ImportError(
        "The tetheria_reference directory is missing. Restore the linked "
        "aero_webcam_teleop repository beside this package."
    )

__path__.append(str(_REFERENCE_DIR))

from .mediapipe_mocap import HandMocap, MediaPipeMocap
from .mediapipe_retargeting import MediaPipeRetargeting, RetargetingConfig

__all__ = [
    "HandMocap",
    "MediaPipeMocap",
    "MediaPipeRetargeting",
    "RetargetingConfig",
]

