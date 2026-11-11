"""Run ONE ordinary video (e.g. a staged fall filmed on a phone) through Kawan's real pipeline.

Same pose model and settings as the browser (pose_landmarker_lite, VIDEO mode, 1 person, 15 fps),
then app.pose + app.fall_detector exactly as the live app. No padding: the person must stay down
in the video itself. Writes the per-frame landmarks next to the video and prints Kawan's verdict.

    D:/kawan-eval/.venv/Scripts/python -I backend/eval/analyse_video.py D:/kawan-eval/own/fall.mp4
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ → import app.*

from app.config import Settings  # noqa: E402
from app.fall_detector import FallDetector  # noqa: E402
from app.pose import motion_score, observation_from_points  # noqa: E402

TARGET_FPS = 15
MODEL = Path(__file__).resolve().parents[2] / "frontend" / "models" / "pose_landmarker_lite.task"


def extract(video: Path) -> list:
    cap = cv2.VideoCapture(str(video))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
    )
    frames, i, next_t = [], 0, 0.0
    with vision.PoseLandmarker.create_from_options(options) as lm:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            t = i / src_fps
            i += 1
            if t + 1e-6 < next_t:
                continue  # sample at 15 fps like the browser
            next_t += 1 / TARGET_FPS
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            res = lm.detect_for_video(image, int(len(frames) * 1000 / TARGET_FPS))
            if res.pose_landmarks:
                frames.append(
                    [[round(p.x, 4), round(p.y, 4), round(p.visibility, 4)] for p in res.pose_landmarks[0]]
                )
            else:
                frames.append(None)
    return frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    args = ap.parse_args()
    frames = extract(args.video)
    out = args.video.with_suffix(".poses.json")
    out.write_text(json.dumps({"fps": TARGET_FPS, "frames": frames}))

    det, prev = FallDetector(Settings()), None
    print(f"{len(frames)} frames at {TARGET_FPS} fps, person found in {sum(f is not None for f in frames)}")
    for k, points in enumerate(frames):
        obs = observation_from_points(
            points, t=k / TARGET_FPS, motion=motion_score(prev, points) if points else None
        )
        prev = points
        if k % 5 == 0:
            torso = f"{obs.torso_len:.2f}" if obs.torso_len else "  - "
            print(
                f"  {k / TARGET_FPS:5.1f}s  {obs.posture:<16} angle {obs.torso_angle:5.1f}  hip {obs.hip_y:.2f}  torso {torso}"
            )
        if d := det.update(obs):
            print(f"\nKAWAN: {d.kind} at {d.t:.1f} s (frame {k})")
            for r in d.reasons:
                print("  ·", r)
            print("  uncertainty:", d.uncertainty)
    print("\nposes saved to", out)


if __name__ == "__main__":
    main()
