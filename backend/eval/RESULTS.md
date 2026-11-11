# Fall detector evaluation — UR Fall Detection Dataset

Run on 2026-11-11 (fall drop measured in torso lengths; walking-towards-camera check added the same day).

## Method

- **Data:** UR Fall Detection Dataset (Kwolek & Kepski 2014), camera 0 (side view, 640×480, 30 fps):
  **30 fall clips** and **40 everyday-activity (ADL) clips**. Licence CC BY-NC-SA 4.0 — the videos are
  NOT in this repo; download them to a folder outside it.
- **Pose:** `extract_poses.py` runs the same model and settings as the browser app
  (`pose_landmarker_lite`, VIDEO mode, 1 person, 15 fps).
- **Detector:** `evaluate.py` feeds every frame through `app.pose` and `app.fall_detector` exactly as the
  live app does. A fall clip passes if it produces a "possible fall"; an ADL clip passes if it produces none.
- **Clip ending:** the dataset clips end 0–2 s after the person lands, but Kawan waits 2 s before acting.
  So the last frame is held for 10 s after each clip ("the person stays where they ended up"). The same
  padding is applied to ADL clips, so lying down on a bed is still tested.

## Results

| Rule | Falls caught | ADL clips with no false alarm |
|---|---|---|
| Old: hip drop ≥ 20% of frame height | 17 / 30 (56.7%) | 36 / 40 (90.0%) |
| Torso-length rule (0.6 torso lengths) | 27 / 30 (90.0%) | 27 / 40 (67.5%) |
| **Current: + "walking towards the camera" check** | **27 / 30 (90.0%)** | **28 / 40 (70.0%)** |

- Missed falls: `fall-03`, `fall-13`, `fall-23`.
- False check-ins: `adl-18, 20, 21, 22, 23, 30, 31, 32, 33, 35, 39, 40`. By the dataset's own frame labels,
  10 of these 12 clips contain the person **lying down** (on a bed or the floor) — the known limitation
  that Kawan handles by checking in ("Are you okay?") before alerting anyone.

**Walking-towards-the-camera check** (added after the team's own test video): walking up to the camera
moves the hips down the picture and then out of view, which looked like "drop, then out of view". The
person grows on screen while a falling torso looks the same or shorter, so a drop is ignored when the torso
is now more than `max_growth` = 1.5× its upright size. It removed the false alarm in the team's video
(the real fall in the same video is still detected at 4.7 s) and one UR Fall false check-in (`adl-38`),
with no fall lost.

Threshold sweep (`--sweep`, measured before the walking-towards-camera check):

| Setting | Falls caught | ADL clean |
|---|---|---|
| torso × 0.3 / 0.4 / 0.5 | 27 / 27 / 27 | 25 / 27 / 25 |
| torso × 0.6 (current) | 27 | 27 |
| torso × 0.7 / 0.8 | 26 / 25 | 28 / 27 |
| torso × 1.0 / 1.2 | 20 / 18 | 31 / 32 |
| still 1 s / 2 s / 3 s | 27 / 27 / 26 | 26 / 27 / 30 |

Kept at 0.6 torso lengths and 2 s: for a safety tool a missed fall costs more than one extra check-in.

## Reproduce

```bash
# once: a separate venv OUTSIDE the repo (keeps mediapipe out of the app's requirements)
python -m venv D:/kawan-eval/.venv
D:/kawan-eval/.venv/Scripts/pip install mediapipe opencv-python-headless
# download fall-XX-cam0-rgb.zip (01-30) and adl-XX-cam0-rgb.zip (01-40) from
# https://fenix.ur.edu.pl/~mkepski/ds/uf.html into D:/kawan-eval/data
D:/kawan-eval/.venv/Scripts/python -I backend/eval/extract_poses.py --data D:/kawan-eval/data --out D:/kawan-eval/poses
D:/kawan-eval/.venv/Scripts/python backend/eval/evaluate.py --poses D:/kawan-eval/poses           # per-clip table
D:/kawan-eval/.venv/Scripts/python backend/eval/evaluate.py --poses D:/kawan-eval/poses --sweep   # thresholds
```

## Caveats

These are lab recordings of young actors in one room with one camera position. They show the detector works
on real video, not that it is clinically validated.
