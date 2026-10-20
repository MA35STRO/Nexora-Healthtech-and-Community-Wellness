"""Perception: pose landmarks → Observation features.

Default path: the BROWSER runs MediaPipe on the user's own webcam and sends only 33 landmark
points per frame (no images) to /ws/perception → `observation_from_points()`.
Optional path (CAMERA_MODE=server): OpenCV + MediaPipe in Python on this machine (`Camera`).

Privacy: frames are processed in memory only; nothing is saved; no video leaves the device.
"""
import math
import threading
import time
from types import SimpleNamespace
from typing import Callable, Optional

from .models import Observation

# MediaPipe pose landmark indices
L_SH, R_SH, L_HIP, R_HIP, L_KNEE, R_KNEE = 11, 12, 23, 24, 25, 26
SKELETON = [(11, 12), (11, 23), (12, 24), (23, 24), (23, 25), (24, 26), (25, 27), (26, 28),
            (11, 13), (13, 15), (12, 14), (14, 16)]


VISIBLE = 0.5


def pose_features(lm) -> tuple[float, float, str, bool]:
    """From landmarks → (torso angle from vertical in degrees, hip y, posture label, full_body).

    MediaPipe *guesses* landmarks that are out of frame; `visibility` tells us which are real.
    """
    seen = lambda *ids: all(lm[i].visibility >= VISIBLE for i in ids)
    sx, sy = (lm[L_SH].x + lm[R_SH].x) / 2, (lm[L_SH].y + lm[R_SH].y) / 2
    hx, hy = (lm[L_HIP].x + lm[R_HIP].x) / 2, (lm[L_HIP].y + lm[R_HIP].y) / 2
    angle = math.degrees(math.atan2(abs(hx - sx), abs(hy - sy) + 1e-6))   # 0 = upright

    if not seen(L_SH, R_SH, L_HIP, R_HIP):
        return angle, hy, "upper body only", False

    torso_len = math.hypot(hx - sx, hy - sy) + 1e-6
    ky = (lm[L_KNEE].y + lm[R_KNEE].y) / 2
    if angle >= 60:
        posture = "lying"
    elif not seen(L_KNEE, R_KNEE):
        posture = "upright"
    elif (ky - hy) / torso_len < 0.5:   # knees roughly level with hips → thighs horizontal
        posture = "sitting"
    else:
        posture = "standing"
    return angle, hy, posture, True


def motion_score(prev: Optional[list], cur: list) -> Optional[float]:
    """Mean movement of confidently-seen landmarks between two frames (same formula as the browser)."""
    if not prev:
        return None
    moves = [math.hypot(c[0] - p[0], c[1] - p[1]) for p, c in zip(prev, cur)
             if p[2] >= VISIBLE and c[2] >= VISIBLE]
    return sum(moves) / len(moves) if moves else None


def observation_from_points(points: Optional[list], t: float, motion: Optional[float] = None) -> Observation:
    """Browser landmarks [[x, y, visibility], ...] (33 of them) → Observation. Reuses pose_features()."""
    if not points or len(points) < 29:
        return Observation(t, False, source="camera", motion=motion)
    lm = [SimpleNamespace(x=float(p[0]), y=float(p[1]), visibility=float(p[2]) if len(p) > 2 else 1.0)
          for p in points]
    angle, hip, posture, full = pose_features(lm)
    return Observation(t, True, angle, hip, posture, "camera", full, motion)


class Camera:
    def __init__(self, index: int, model_path: str, on_obs: Callable[[Observation], None]):
        self.index, self.model_path, self.on_obs = index, model_path, on_obs
        self.running = False
        self.error: Optional[str] = None
        self.fps = 0.0
        self.last_jpeg: Optional[bytes] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.error = None
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=3)
        self.last_jpeg = None

    def _loop(self):
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self._cv2 = cv2
        try:
            landmarker = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=self.model_path),
                running_mode=vision.RunningMode.VIDEO, num_poses=1))
        except Exception as e:
            self.error, self.running = f"Pose model failed to load: {e}", False
            return
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.error, self.running = f"Camera {self.index} could not be opened", False
            return

        t0, last_ts, frames, fps_t = time.time(), -1, 0, time.time()
        prev = None
        try:
            while self.running:
                ok, frame = cap.read()
                if not ok:
                    self.error = "Camera stopped delivering frames"
                    break
                now = time.time()
                ts = max(last_ts + 1, int((now - t0) * 1000))   # MediaPipe needs increasing timestamps
                last_ts = ts
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)

                if result.pose_landmarks:
                    lm = result.pose_landmarks[0]
                    angle, hip, posture, full = pose_features(lm)
                    pts = [(p.x, p.y, p.visibility) for p in lm]
                    motion = motion_score(prev, pts)
                    prev = pts
                    self.on_obs(Observation(now, True, angle, hip, posture, "camera", full, motion))
                    self._draw(frame, lm, f"{posture}  torso {angle:.0f} deg")
                else:
                    self.on_obs(Observation(now, False, source="camera"))
                    self._label(frame, "no person detected")

                ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    self.last_jpeg = jpg.tobytes()
                frames += 1
                if now - fps_t >= 1:
                    self.fps, frames, fps_t = frames / (now - fps_t), 0, now
        finally:
            cap.release()
            landmarker.close()
            self.running = False

    @staticmethod
    def _draw(frame, lm, text):
        import cv2
        h, w = frame.shape[:2]
        pts = {i: (int(p.x * w), int(p.y * h)) for i, p in enumerate(lm)}
        for a, b in SKELETON:
            cv2.line(frame, pts[a], pts[b], (230, 200, 40), 3)
        for i in (11, 12, 23, 24, 25, 26):
            cv2.circle(frame, pts[i], 5, (255, 255, 255), -1)
        Camera._label(frame, text)

    @staticmethod
    def _label(frame, text):
        import cv2
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 30), (40, 30, 20), -1)
        cv2.putText(frame, text, (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
