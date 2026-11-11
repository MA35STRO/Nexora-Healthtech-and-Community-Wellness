"""Builds data-driven poster assets (run with the eval venv: segno is needed for QR codes).

    D:/kawan-eval/.venv/Scripts/python poster/tools/make_assets.py --poses D:/kawan-eval/poses

- assets/qr/github.svg, assets/qr/video.svg   QR codes (vector)
- assets/figures/fall-sequence.svg            REAL MediaPipe skeleton from UR Fall clip fall-04 (CC BY-NC-SA 4.0,
                                              Kwolek & Kepski 2014) at four moments, with the app's own measurements
- assets/screens/tiles/*.png                  feature-tile crops of the app screenshots
"""

import argparse
import json
import sys
from pathlib import Path

import segno

POSTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POSTER.parent / "backend"))
from app.pose import observation_from_points  # noqa: E402

GITHUB = "https://github.com/MA35STRO/Nexora-Healthtech-and-Community-Wellness"
VIDEO = "https://drive.google.com/drive/folders/1YvF9wa3N2mt3SOXe9MK3IwnZqf-68v54?usp=sharing"

# MediaPipe Pose body connections (face points left out: a skeleton, not a face)
BONES = [
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),  # shoulders, arms
    (11, 23),
    (12, 24),
    (23, 24),  # torso
    (23, 25),
    (25, 27),
    (24, 26),
    (26, 28),  # legs
    (27, 31),
    (28, 32),  # feet
]
BODY = sorted({i for b in BONES for i in b})


def qr(url: str, out: Path):
    segno.make(url, error="m").save(
        out, kind="svg", scale=10, border=0, dark="#0b1a24", light=None
    )


def fall_sequence(
    poses: Path, out: Path, frames=(0, 14, 22, 34), clip="fall-04", dark=False
):
    # dark=True: captions for a dark poster section (v2 redesign)
    cap_main, cap_sub, panel = (
        ("#e9f6f4", "#8fb5b8", "#0e2c3a") if dark else ("#0b1a24", "#3c5562", "#0f2633")
    )
    data = json.loads((poses / f"{clip}.json").read_text())
    fps = data["fps"]
    picks = [(i, data["frames"][i]) for i in frames]

    # one shared crop over all chosen frames, so the downward movement stays visible
    xs = [p[k][0] for _, p in picks for k in BODY]
    ys = [p[k][1] for _, p in picks for k in BODY]
    x0, x1 = min(xs) - 0.04, max(xs) + 0.04
    y0, y1 = min(ys) - 0.05, max(ys) + 0.03
    aspect = 640 / 480  # UR Fall cam0 frames are 640×480
    pw, ph = 300, 300 * (y1 - y0) / ((x1 - x0) * aspect)  # panel size in svg units
    gap, label_h = 26, 92
    W = len(picks) * pw + (len(picks) - 1) * gap
    H = ph + label_h

    def px(x, y, col):
        return col * (pw + gap) + (x - x0) / (x1 - x0) * pw, (y - y0) / (y1 - y0) * ph

    captions = ["upright", "tipping over", "hips dropping fast", "on the floor"]
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
        f'font-family="JetBrains Mono, monospace">'
    ]
    for col, (i, p) in enumerate(picks):
        o = observation_from_points(p, i / fps)
        left = col * (pw + gap)
        svg.append(
            f'<rect x="{left:.1f}" y="0" width="{pw}" height="{ph:.1f}" rx="18" fill="{panel}"/>'
        )
        # floor line at the lowest foot position across the sequence
        floor = (
            (max(p2[k][1] for _, p2 in picks for k in (27, 28, 31, 32)) - y0)
            / (y1 - y0)
            * ph
        )
        svg.append(
            f'<line x1="{left + 14:.1f}" y1="{floor:.1f}" x2="{left + pw - 14:.1f}" y2="{floor:.1f}" '
            f'stroke="#2b4a59" stroke-width="3" stroke-dasharray="8 8"/>'
        )
        for a, b in BONES:
            (ax, ay), (bx, by) = px(*p[a][:2], col), px(*p[b][:2], col)
            torso = (a, b) in ((11, 23), (12, 24), (11, 12), (23, 24))
            svg.append(
                f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
                f'stroke="{"#5fe0c8" if torso else "#2fb8a8"}" stroke-width="{7 if torso else 5}" '
                f'stroke-linecap="round"/>'
            )
        for k in BODY:
            x, y = px(*p[k][:2], col)
            svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#d9fff6"/>')
        hx, hy = px((p[23][0] + p[24][0]) / 2, (p[23][1] + p[24][1]) / 2, col)
        svg.append(
            f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="11" fill="#f5a524" stroke="#0f2633" stroke-width="3"/>'
        )
        svg.append(
            f'<text x="{left + 16:.1f}" y="36" font-size="24" font-weight="700" fill="#9fe8da">{i / fps:.1f} s</text>'
        )
        svg.append(
            f'<text x="{left + pw / 2:.1f}" y="{ph + 38:.1f}" font-size="25" font-weight="700" '
            f'text-anchor="middle" fill="{cap_main}" font-family="Plus Jakarta Sans, sans-serif">{captions[col]}</text>'
        )
        svg.append(
            f'<text x="{left + pw / 2:.1f}" y="{ph + 74:.1f}" font-size="21" text-anchor="middle" '
            f'fill="{cap_sub}">torso {o.torso_angle:.0f}° · hip {o.hip_y:.2f}</text>'
        )
    svg.append("</svg>")
    out.write_text("\n".join(svg), encoding="utf-8")


# Feature-tile crops (x0, y0, x1, y1) in pixels of the screenshots from
# frontend/scripts/take-poster-screenshots.mjs. Daily check-ins come from the full-page shot,
# because the chart may not have finished drawing when its card is captured on its own.
TILES = {
    "fall-alert": ("caregiver-alert.png", (37, 330, 1820, 1373)),
    "phone-bm": ("mobile.png", (0, 640, 1170, 2532)),
    "adherence": ("adherence.png", (0, 0, 1075, 895)),
    "vitals": ("vitals.png", (0, 0, 1420, 895)),
    "answer": ("answer-with-source.png", (0, 0, 1770, 880)),
    "checkins": ("caregiver-full.png", (1725, 2450, 3240, 3180)),
    "hero-checkin": ("companion-checkin.png", (0, 0, 1770, 870)),
}


def crop_tiles():
    import cv2  # opencv-python-headless (installed in the eval venv)

    screens = POSTER / "assets" / "screens"
    (screens / "tiles").mkdir(exist_ok=True)
    for name, (src, (x0, y0, x1, y1)) in TILES.items():
        cv2.imwrite(
            str(screens / "tiles" / f"{name}.png"),
            cv2.imread(str(screens / src))[y0:y1, x0:x1],
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", type=Path, required=True)
    args = ap.parse_args()
    (POSTER / "assets" / "qr").mkdir(parents=True, exist_ok=True)
    (POSTER / "assets" / "figures").mkdir(parents=True, exist_ok=True)
    qr(GITHUB, POSTER / "assets" / "qr" / "github.svg")
    qr(VIDEO, POSTER / "assets" / "qr" / "video.svg")
    fall_sequence(args.poses, POSTER / "assets" / "figures" / "fall-sequence.svg")
    fall_sequence(
        args.poses, POSTER / "assets" / "figures" / "fall-sequence-dark.svg", dark=True
    )
    crop_tiles()
    print("assets written to", POSTER / "assets")


if __name__ == "__main__":
    main()
