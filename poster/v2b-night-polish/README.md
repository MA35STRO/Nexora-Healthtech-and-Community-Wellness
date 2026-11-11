# Kawan poster V2B — "Night Polish"

The final art-direction pass on **V2A Night** (`../v2/`). Same visual identity, section order and facts;
refined typography, balance and accuracy. V2A is kept unchanged apart from two accuracy updates noted below.

## Files

| Path | What it is |
|---|---|
| `poster.html` | Editable source (HTML/CSS + inline SVG); assets come from `../assets/` |
| `build.mjs` | `node poster/v2b-night-polish/build.mjs` → PDFs + preview, warns about overflow |
| `out/kawan-poster-v2B-night-polish.pdf` | **Final A1 print file** (594 × 841 mm, fonts embedded) |
| `out/kawan-poster-v2B-night-polish-bleed3mm.pdf` | Same with 3 mm bleed (600 × 847 mm) |
| `out/preview.png` | Preview image |

## Changelog (V2A Night → V2B Night Polish)

**Accuracy**
- Everyday-clip check-ins are now **12 / 40 (10 of them lying down on purpose)**, not 13 / 40: the
  walking-towards-the-camera fix (found with the team's own test video) removed one false check-in on the
  UR Fall dataset, with no fall lost (27 / 30 unchanged). See `backend/eval/RESULTS.md`.
- New, code-verified line under "Needs internet": if the internet drops, detection and check-ins keep
  running on the hub PC, Claude answers fall back to the offline library, and phone alerts and voice input stop.
- MediaPipe (ref 6) is now cited where it is used; every reference number matches its claim.

**Typography & readability**
- Architecture labels enlarged from ~11 pt to ~13 pt print size, with fewer words per box
  ("Talk · tap · type", "raw video stays local", "Safety engine · R1–R10").
- Body minimum raised: privacy, test conditions, offline lists and captions 13–14 pt; references 12.5 pt.
- Wording trimmed instead of shrinking text (privacy bullets, test conditions, fall panel output on 2 lines).
- Consistent curly quotation marks throughout.

**Testimonials**
- Restored the **full approved wording** of all four quotes (two had been shortened in V2A) with proper
  opening and closing quotation marks, equal-height cards and no clipping.
- "What we heard → what we did" shown as three aligned cards.

**Results**
- Three-column layout: evaluation · **148 automated tests** · feedback. The tests metric is now a glowing
  donut chart with a 117 / 19 / 12 breakdown (pytest, Vitest, Playwright) instead of a flat banner.
- Evaluation card keeps the 90 % ring, one dot per clip, the check-in ≠ alert ladder, test conditions and the
  "not real-world accuracy, not clinically validated" warning.

**Guardian mascot**
- The real app mascot is unchanged (so it matches the screenshots), but now stands inside a **protective
  shield** outline with the notice → ask → alert signal nodes on it; the hero column is wider for balance.

**Balance & finish**
- One corner radius for all panels (5 mm), equal 4.6 mm spacing between the light sections.
- Fall panel uses the team's staged fall with the **face blurred** (privacy) and the real detector output.
- Footer: consistent reference format, larger text, 30 mm QR codes (both verified to decode).
