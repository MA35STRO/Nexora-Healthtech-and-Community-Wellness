"""Step 2 of the fall-detector evaluation: body points → Kawan's REAL fall detector → scores (fast).

Each UR Fall sequence (from extract_poses.py) is fed frame by frame through app.pose and
app.fall_detector exactly as the live app does. A fall clip should give one "possible fall";
an everyday-activity (ADL) clip should give none.

The dataset clips stop ~0-2 s after the person lands, but Kawan deliberately waits still_s (2 s)
before alerting. So after each clip we HOLD THE LAST FRAME for --hold seconds, i.e. "the person
stays where they ended up". That is the case Kawan exists for (can't get up). The same padding is
applied to ADL clips, so lying down on a bed is still tested for false alarms.

    python evaluate.py --poses D:/kawan-eval/poses            # current settings, per-clip table
    python evaluate.py --poses D:/kawan-eval/poses --sweep    # compare thresholds + the old rule
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ → import app.*

from app.config import Settings  # noqa: E402
from app.fall_detector import FallDetector  # noqa: E402
from app.pose import motion_score, observation_from_points  # noqa: E402


def load(poses_dir: Path) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in sorted(poses_dir.glob("*.json"))}


def run(seq: dict, cfg: Settings, hold_s: float, frame_rule: bool = False) -> list:
    """Returns the detections for one sequence. frame_rule=True simulates the OLD 20%-of-frame rule."""
    fps = seq["fps"]
    frames = seq["frames"]
    last = frames[-1] if frames else None
    frames = frames + [last] * int(hold_s * fps)
    det, prev, out = FallDetector(cfg), None, []
    for i, points in enumerate(frames):
        motion = motion_score(prev, points) if points else None
        obs = observation_from_points(points, t=i / fps, motion=motion)
        if frame_rule:
            obs = dataclasses.replace(obs, torso_len=None)
        if d := det.update(obs):
            out.append(d)
        prev = points
    return out


def score(data: dict, cfg: Settings, hold_s: float, frame_rule: bool = False) -> dict:
    caught, false_alarms, missed, alarm_clips = 0, 0, [], []
    falls = [k for k in data if k.startswith("fall")]
    adls = [k for k in data if k.startswith("adl")]
    for k in falls:
        if run(data[k], cfg, hold_s, frame_rule):
            caught += 1
        else:
            missed.append(k)
    for k in adls:
        if n := len(run(data[k], cfg, hold_s, frame_rule)):
            false_alarms += n
            alarm_clips.append(k)
    return {
        "falls": len(falls),
        "caught": caught,
        "adls": len(adls),
        "false_alarm_clips": len(alarm_clips),
        "missed": missed,
        "alarm_clips": alarm_clips,
    }


def line(name: str, r: dict) -> str:
    recall = r["caught"] / r["falls"] if r["falls"] else 0
    spec = 1 - r["false_alarm_clips"] / r["adls"] if r["adls"] else 0
    return (
        f"{name:<28} falls caught {r['caught']:>2}/{r['falls']:<2} ({recall:6.1%})   "
        f"everyday clips with NO false alarm {r['adls'] - r['false_alarm_clips']:>2}/{r['adls']:<2} ({spec:6.1%})"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", type=Path, required=True)
    ap.add_argument("--hold", type=float, default=10.0, help="seconds to hold the last frame after a clip")
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()
    data = load(args.poses)
    base = Settings()

    if not args.sweep:
        for k, seq in data.items():
            dets = run(seq, base, args.hold)
            seen = sum(f is not None for f in seq["frames"])
            verdict = "FALL" if dets else "-"
            print(f"{k:<8} {len(seq['frames']):>4} frames  person in {seen:>4}  → {verdict}")
            for d in dets:
                for r in d.reasons:
                    print(f"           · {r}")
        r = score(data, base, args.hold)
        print()
        print(line(f"current (torso × {base.min_drop_torso})", r))
        print("missed:", ", ".join(r["missed"]) or "none")
        print("false alarms:", ", ".join(r["alarm_clips"]) or "none")
        return

    print(line("OLD rule (20% of frame)", score(data, base, args.hold, frame_rule=True)))
    for x in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2):
        cfg = dataclasses.replace(base, min_drop_torso=x)
        print(line(f"torso × {x}", score(data, cfg, args.hold)))
    print()
    for still in (1.0, 2.0, 3.0):
        cfg = dataclasses.replace(base, still_s=still)
        print(line(f"torso × {base.min_drop_torso}, still {still:.0f}s", score(data, cfg, args.hold)))


if __name__ == "__main__":
    main()
