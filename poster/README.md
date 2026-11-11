# Kawan — A1 poster (UTP CodeFest '26 Grand Finale)

**Print files:** `out/kawan-poster-A1.pdf` (594 × 841 mm) and `out/kawan-poster-A1-bleed3mm.pdf`
(600 × 847 mm, 3 mm bleed — use this one if the print shop asks for bleed). Fonts are embedded.

## Files

| Path | What it is |
|---|---|
| `CONTENT.md` | Approved poster text and references (source of truth) |
| `poster.html` | Editable poster: HTML/CSS laid out in mm at A1 |
| `build.mjs` | Renders the PDFs + `out/preview.png`, and warns about anything off the page |
| `assets/screens/` | High-resolution screenshots of the running app (demo mode, labelled SIMULATED) |
| `assets/screens/tiles/` | Crops used in the feature tiles and header |
| `assets/figures/fall-sequence.svg` | Real MediaPipe skeleton from UR Fall clip fall-04 |
| `assets/qr/` | QR codes: demo video (Google Drive) and GitHub repo |
| `assets/logos/` | UTP (official SVG from utp.edu.my) and CodeFest '26 logos |
| `assets/fonts/` | Sora, Plus Jakarta Sans, JetBrains Mono (SIL Open Font Licence, files included) |
| `tools/make_assets.py` | Rebuilds QR codes, skeleton figure and tile crops |

**Licences:** the poster's code is MIT like the rest of the repo, except `assets/figures/fall-sequence.svg`
(derived from the UR Fall Detection Dataset: CC BY-NC-SA 4.0, non-commercial) and the UTP / CodeFest logos
(property of their owners, used for this competition entry only).

## Edit and rebuild

1. Edit text in `poster.html` (keep `CONTENT.md` in step).
2. `node poster/build.mjs` (uses Playwright from `frontend/node_modules`).
3. Check `out/preview.png`, and that the build printed no ⚠ warnings.

**Adding the team photo:** save it as `assets/photos/kawan-in-use.jpg`, then in `poster.html` change the
`hero-shot` image `src` and its caption (search for `PHOTO SLOT`). Landscape, about 16:10, at least 2000 px wide.

**New screenshots:** run the backend with `KAWAN_DB=:memory: SEED_DEMO_HISTORY=1 VITALS_SIM=1` on a free port,
then `node frontend/scripts/take-poster-screenshots.mjs http://127.0.0.1:<port>`, then `tools/make_assets.py`.
