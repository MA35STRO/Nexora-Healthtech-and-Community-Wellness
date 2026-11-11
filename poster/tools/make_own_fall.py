"""Poster figure from a team member's staged-fall video: real frames + the REAL MediaPipe skeleton.

Needs the video and its landmarks from backend/eval/analyse_video.py (same model and settings as the app):

    D:/kawan-eval/.venv/Scripts/python -I poster/tools/make_own_fall.py D:/kawan-eval/own/fall-ajmal.mp4

Writes poster/assets/figures/own-fall-sequence.png. Nothing is drawn by hand: every line joins two
landmarks the model detected in that exact frame. The face is blurred by default (privacy).
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

POSTER = Path(__file__).resolve().parents[1]
BONES = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24),
         (23, 25), (25, 27), (24, 26), (26, 28), (27, 31), (28, 32)]  # fmt: skip
TORSO = {(11, 23), (12, 24), (11, 12), (23, 24)}
FPS = 15
UP = 3  # upscale before drawing so lines stay crisp in print


def frame_at(cap, t):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    if not ok:
        raise SystemExit(f"no frame at {t}s")
    return img


FACE = range(0, 11)  # MediaPipe: nose, eyes, ears, mouth


def blur_face(img, pts, w, h):
    """Privacy: blur a soft oval over the face, located from the face landmarks of this frame."""
    face = np.array([(pts[i][0] * w * UP, pts[i][1] * h * UP) for i in FACE])
    cx, cy = face.mean(axis=0)
    shoulders = np.hypot((pts[11][0] - pts[12][0]) * w * UP, (pts[11][1] - pts[12][1]) * h * UP)
    r = max(np.linalg.norm(face - (cx, cy), axis=1).max() * 1.9, shoulders * 0.42, 40)
    x0, y0 = max(int(cx - r), 0), max(int(cy - r * 1.15), 0)
    x1, y1 = min(int(cx + r), img.shape[1]), min(int(cy + r * 1.15), img.shape[0])
    roi = img[y0:y1, x0:x1]
    if roi.size == 0:
        return img
    small = cv2.resize(roi, (max(roi.shape[1] // 18, 1), max(roi.shape[0] // 18, 1)), interpolation=cv2.INTER_AREA)
    blurred = cv2.GaussianBlur(cv2.resize(small, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_LINEAR), (0, 0), 9)
    mask = np.zeros(roi.shape[:2], np.float32)
    cv2.ellipse(mask, (int(cx - x0), int(cy - y0)), (int(r), int(r * 1.15)), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
    mask = cv2.GaussianBlur(mask, (0, 0), r * 0.15)[..., None]
    img[y0:y1, x0:x1] = (blurred * mask + roi * (1 - mask)).astype(np.uint8)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--times", default="1.0,2.9,4.47,7.0", help="seconds of the four panels")
    ap.add_argument("--crop", default="0.21,0.71", help="x range (fractions) that contains the person")
    ap.add_argument("--ytop", type=float, default=0.07, help="trim this fraction of empty space above the head")
    ap.add_argument("--no-blur", action="store_true", help="keep the face sharp (default: blurred for privacy)")
    args = ap.parse_args()
    poses = json.loads(args.video.with_suffix(".poses.json").read_text())["frames"]
    cap = cv2.VideoCapture(str(args.video))
    x0f, x1f = (float(v) for v in args.crop.split(","))
    panels = []
    for t in (float(v) for v in args.times.split(",")):
        img = frame_at(cap, t)
        h, w = img.shape[:2]
        img = cv2.resize(img, (w * UP, h * UP), interpolation=cv2.INTER_CUBIC)
        img = cv2.addWeighted(img, 0.78, np.full_like(img, (39, 24, 8)), 0.22, 0)  # navy tint so the skeleton pops
        pts = poses[min(round(t * FPS), len(poses) - 1)]
        if pts and not args.no_blur:
            img = blur_face(img, pts, w, h)
        if pts:
            P = [(int(p[0] * w * UP), int(p[1] * h * UP)) for p in pts]
            for a, b in BONES:
                col = (200, 240, 95) if (a, b) in TORSO else (190, 198, 22)  # BGR: mint / cyan
                cv2.line(img, P[a], P[b], (12, 24, 8), 15, cv2.LINE_AA)
                cv2.line(img, P[a], P[b], col, 8, cv2.LINE_AA)
            for k in {i for bone in BONES for i in bone}:
                cv2.circle(img, P[k], 8, (246, 255, 217), -1, cv2.LINE_AA)
            hip = ((P[23][0] + P[24][0]) // 2, (P[23][1] + P[24][1]) // 2)
            cv2.circle(img, hip, 17, (12, 24, 8), -1, cv2.LINE_AA)
            cv2.circle(img, hip, 13, (105, 191, 255), -1, cv2.LINE_AA)  # amber hip centre
        panels.append(img[int(args.ytop * h * UP) :, int(x0f * w * UP) : int(x1f * w * UP)])
    gap = np.full((panels[0].shape[0], 18, 3), (39, 24, 8), np.uint8)
    sheet = panels[0]
    for p in panels[1:]:
        sheet = np.hstack([sheet, gap, p])
    out = POSTER / "assets" / "figures" / "own-fall-sequence.png"
    cv2.imwrite(str(out), sheet)
    print("wrote", out, sheet.shape[1], "x", sheet.shape[0])


if __name__ == "__main__":
    main()
