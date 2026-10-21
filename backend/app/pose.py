"""Body pose → simple numbers the safety rules can reason about.

The BROWSER runs MediaPipe Pose on the user's own webcam and sends only 33 body points per frame
(x, y and how visible each point is) — never images. This file turns those points into:

    torso angle   0° = upright, 90° = lying flat
    hip height    0 = top of the picture, 1 = bottom
    posture       "standing" / "sitting" / "lying" / ...
    motion        how much the body moved since the last frame

MediaPipe point numbers used here: 11/12 shoulders, 23/24 hips, 25/26 knees.
"""

import math
from types import SimpleNamespace
from typing import Optional

from .data_types import Observation

LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_KNEE, RIGHT_KNEE = 25, 26

# MediaPipe also *guesses* points that are out of view; visibility says how sure it is.
VISIBLE = 0.5


def pose_features(points) -> tuple[float, float, str, bool]:
    """Returns (torso angle in degrees, hip height, posture label, whole torso really visible?)."""

    def seen(*ids):
        return all(points[i].visibility >= VISIBLE for i in ids)

    shoulder_x = (points[LEFT_SHOULDER].x + points[RIGHT_SHOULDER].x) / 2
    shoulder_y = (points[LEFT_SHOULDER].y + points[RIGHT_SHOULDER].y) / 2
    hip_x = (points[LEFT_HIP].x + points[RIGHT_HIP].x) / 2
    hip_y = (points[LEFT_HIP].y + points[RIGHT_HIP].y) / 2

    # Angle of the shoulder→hip line from vertical: 0° upright, 90° horizontal.
    angle = math.degrees(math.atan2(abs(hip_x - shoulder_x), abs(hip_y - shoulder_y) + 1e-6))

    if not seen(LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP):
        return angle, hip_y, "upper body only", False  # hips were guessed: don't trust this frame

    torso_length = math.hypot(hip_x - shoulder_x, hip_y - shoulder_y) + 1e-6
    knee_y = (points[LEFT_KNEE].y + points[RIGHT_KNEE].y) / 2
    if angle >= 60:
        posture = "lying"
    elif not seen(LEFT_KNEE, RIGHT_KNEE):
        posture = "upright"
    elif (knee_y - hip_y) / torso_length < 0.5:  # knees about level with hips → thighs horizontal
        posture = "sitting"
    else:
        posture = "standing"
    return angle, hip_y, posture, True


def motion_score(previous: Optional[list], current: list) -> Optional[float]:
    """Average distance the clearly-visible points moved between two frames (same formula as the browser)."""
    if not previous:
        return None
    moves = [
        math.hypot(c[0] - p[0], c[1] - p[1])
        for p, c in zip(previous, current)
        if p[2] >= VISIBLE and c[2] >= VISIBLE
    ]
    return sum(moves) / len(moves) if moves else None


def observation_from_points(points: Optional[list], t: float, motion: Optional[float] = None) -> Observation:
    """One browser frame [[x, y, visibility] × 33] → an Observation for the safety rules."""
    if not points or len(points) < 29:
        return Observation(t, person=False, source="camera", motion=motion)
    landmarks = [
        SimpleNamespace(x=float(p[0]), y=float(p[1]), visibility=float(p[2]) if len(p) > 2 else 1.0)
        for p in points
    ]
    angle, hip_y, posture, full_body = pose_features(landmarks)
    return Observation(t, True, angle, hip_y, posture, "camera", full_body, motion)
