"""Step 1 of the fall-detector evaluation: video frames → MediaPipe body points (run once, slow).

Reads UR Fall Detection Dataset zips (fall-XX-cam0-rgb.zip, adl-XX-cam0-rgb.zip), runs the SAME pose
model and settings as the browser (pose_landmarker_lite, VIDEO mode, 1 person, 15 fps) and saves
one JSON per sequence: {"fps": 15, "frames": [[[x, y, visibility] × 33] or null, ...]}.

The dataset is CC BY-NC-SA 4.0 (non-commercial academic use): keep it OUTSIDE the repo.

    python extract_poses.py --data D:/kawan-eval/data --out D:/kawan-eval/poses
"""

import argparse
import json
import re
import zipfile
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

SOURCE_FPS = 30  # UR Fall cam0 is recorded at 30 fps
TARGET_FPS = 15  # what the browser sends (frontend/src/camera/useCamera.ts)
MODEL = Path(__file__).resolve().parents[2] / "frontend" / "models" / "pose_landmarker_lite.task"


def frame_number(name: str) -> int:
    return int(re.findall(r"(\d+)\.png$", name)[0])


def extract(zip_path: Path) -> list:
    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
    )
    frames = []
    with zipfile.ZipFile(zip_path) as z, vision.PoseLandmarker.create_from_options(options) as lm:
        names = sorted((n for n in z.namelist() if n.endswith(".png")), key=frame_number)
        step = SOURCE_FPS // TARGET_FPS
        for i, name in enumerate(names[::step]):
            bgr = cv2.imdecode(np.frombuffer(z.read(name), np.uint8), cv2.IMREAD_COLOR)
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = lm.detect_for_video(image, int(i * 1000 / TARGET_FPS))
            if result.pose_landmarks:
                # same packing as the browser: 4 decimal places
                frames.append(
                    [[round(p.x, 4), round(p.y, 4), round(p.visibility, 4)] for p in result.pose_landmarks[0]]
                )
            else:
                frames.append(None)
    return frames


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for zip_path in sorted(args.data.glob("*-cam0-rgb.zip")):
        seq = zip_path.name.replace("-cam0-rgb.zip", "")
        out = args.out / f"{seq}.json"
        if out.exists():
            continue
        if not zipfile.is_zipfile(zip_path):
            print(f"{seq}: skipped (download not finished)")
            continue
        frames = extract(zip_path)
        out.write_text(json.dumps({"fps": TARGET_FPS, "frames": frames}))
        seen = sum(f is not None for f in frames)
        print(f"{seq}: {len(frames)} frames, person found in {seen}")


if __name__ == "__main__":
    main()
