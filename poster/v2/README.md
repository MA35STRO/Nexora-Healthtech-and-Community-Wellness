# Kawan poster v2 — "The Digital Guardian"

A visual redesign of the A1 poster. **Same facts and text as the refined v1** (`../CONTENT.md`, every claim
checked against the code); only the visual language changed. v1 (`../poster.html`, `../out/`) is untouched.

## Files

| Path | What it is |
|---|---|
| `poster.html` | Editable source for both variations (HTML/CSS + inline SVG) |
| `build.mjs` | `node poster/v2/build.mjs` renders both variations: PDFs (trim + 3 mm bleed) and previews |
| `out/kawan-poster-v2A-night.pdf` | **Variation A · Night Guardian** — dark glowing hero, dark technical sections |
| `out/kawan-poster-v2B-day.pdf` | **Variation B · Daylight** — light hero, deep-teal technical band |
| `out/*-bleed3mm.pdf` | Same, 600 × 847 mm with 3 mm bleed |
| `out/preview-A.png`, `out/preview-B.png` | Quick-look previews |

Open `poster.html` in Chrome for A, or `poster.html?v=day` for B.

## Design system

**Colour roles** (never decorative-only):

| Colour | Hex | Used for |
|---|---|---|
| Midnight Navy | `#081827` | hero, technical and privacy panels, footer |
| Deep Teal / Guardian Cyan | `#087F8C` / `#16C6BE` | Kawan identity, system flows, "works offline" |
| Warm Amber | `#FFBF69` | attention: check-ins, the 80% statistic, everyday-clip triggers, team name |
| Alert Coral | `#FF7272` | emergencies and escalation (Telegram, safety engine, failed alarm) |
| Soft Violet | `#A99BFF` | secondary technical / AI elements (cited library + Claude, "needs internet") |
| Ice White · Pale Mint · Soft Blue | `#F1F7FA` · `#DFF4F1` · `#E8F0FA` | information-heavy sections |

**Typography:** Space Grotesk (headings, big numbers) · Inter (body, ≥ 12.5 pt) · IBM Plex Mono (labels,
technical annotations). All SIL Open Font Licence, embedded in the PDFs (`../assets/fonts/`).

**Visual language:**
- *Guardian halo:* the real app mascot (ported 1:1 from `frontend/src/components/Mascot.tsx`) inside a
  smart-home outline with concentric rings and three signal nodes — notices → asks → alerts.
- *Connected nodes + fine grid:* generated at render time from a fixed seed (same result every build).
- *Glowing paths:* solution steps, the Kawan track in "alarm vs Kawan", and diagram connectors.
- *Honest data graphics:* a 90% ring for 27/30 fall clips, one dot per clip for 13/40 everyday clips,
  a stacked bar for 117/19/12 tests.
- *Device frames:* real screenshots in browser and phone frames (demo data, labelled SIMULATED in the app).

**Print:** A1 portrait 594 × 841 mm, fonts embedded, screenshots captured at 2.5–3× (≈ 300 dpi at size),
QR codes 30 mm (37 × 37 modules, 0.8 mm per module), minimum body text 12.5 pt, references 11.5 pt.
The soft glow effects are blurred shapes that the PDF stores as images; they are meant to be soft.

## Adding the team photo

The hero now uses the mascot. A photo of Kawan in use fits best in section 04 in place of the companion
check-in frame (`localhost / companion`): keep it landscape, at least 2000 px wide.
