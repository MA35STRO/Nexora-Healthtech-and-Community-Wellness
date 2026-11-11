# Kawan — A1 poster content (refined)

Source of truth for the poster text. Every number has a reference or comes from the repo;
every technical claim was checked against the code on 2026-11-11 (see "Verified facts" at the end).
`[n]` = reference number.

---

## HEADER
- Logos: UTP · CODEFEST'26 SYNTECH · "Grand Finale · HealthTech track"
- **Kawan.** — *kawan (Malay) · friend*
- *An AI guardian for people who live alone: it notices, checks in, and alerts family only when needed.*
- **Not a doctor. Not a surveillance camera. A guardian.**
- Team **Nexora** · UTP CODEFEST '26
- Ajmal Haikal bin Mohd Zakhiruddin · Nik Mohamad Fairuz Addailami bin Mohamed Zabedi · Muhammad Iyad Mustaqim bin Muhd Gaddafi · Muhammad Zulfiqar bin Zuraimi
- Hero image: real app screen, check-in after a possible fall (simulated) — **to be replaced by the team photo**

## 01 · THE PROBLEM *(Impact)*
| Stat | Caption |
|---|---|
| **15.6%** | of Malaysian adults have diabetes, 29.2% hypertension; ~4 in 10 don't know it [1] |
| **684k** | people die from falls each year; most fatal falls are in over-60s [2] |
| **80%** | of fallers over 90 couldn't get up alone; 30% lay on the floor ≥ 1 hour [3] |
| **~50%** | of long-term patients don't take medicine as prescribed [4] |

## 02 · OUR SOLUTION
1. **Notice** — camera spots falls and unusual stillness; tracks medicines and readings.
2. **Check in** — "Are you okay?" by voice, button or chat, in English or Malay.
3. **Escalate only if needed** — "Help", a red-flag symptom or no reply in 20 s alerts caregivers.
4. **Explain why** — caregivers see why, and what else it could be.

**Conventional alarm vs Kawan** (Impact strip)
- *Conventional alarm · pendant or panic button:* person falls → they must press the button → hurt or confused: alarm mostly unused [3], no one knows.
- *Kawan · proactive check-in · no panic button, no wearable:* webcam notices the fall → "Are you okay?" → "help" or no reply in 20 s: caregivers alerted, with reasons.

## 03 · HOW IT WORKS *(Technical execution)*
Diagram: Browser (on the device: webcam → MediaPipe pose AI at 15 fps, raw video stays in the browser; voice · buttons · chat; readings typed in or posted by a device; companion screen) → **33 pts** → Kawan hub (Python, same PC: fall detector, inactivity, vitals, medicines, daily check-in, chat router → safety engine R1–R10; questions only → cited health library, optional Claude AI) → People (caregivers' live dashboard; Telegram escalations to every caregiver's phone, optional · internet; doctor report).

Fall inset (real skeleton, UR Fall clip fall-04 [5]): upright → hips drop ≥ 0.6 of their own torso length in ≤ 1.5 s → body horizontal (≥ 60°) or out of view → still down after 2 s → check in. Kawan's own output: "Hip dropped 14% of frame (0.6× torso) in 1.3 s · torso 90° · no recovery within 2 s".

**v2 Variation A fall panel:** "Our own fall test, seen by Kawan" — staged fall onto a floor mat by a team member (D:/kawan-eval/own/fall-ajmal.mp4, not in the repo), analysed by `backend/eval/analyse_video.py` with the app's model and detector. Kawan's real output: possible fall at 4.7 s — "Hip dropped 18% of frame (0.7× torso) in 1.4 s · torso 68° · no recovery within 2 s". Frames + skeleton: `poster/tools/make_own_fall.py`.

## 04 · THE APP *(Usability · real screens, demo data)*
Large screenshots: **Fall alert, with reasons** · **On a phone** (Bahasa Melayu) · **Caregiver dashboard** (vitals, adherence, activity, check-ins).
Also built and working: spoken reminders + missed-dose notice · vitals with sustained-reading alerts · daily check-in triage up to "call 999" · 104 cited health topics EN & BM · one-click doctor report.

## 05 · SAFE & PRIVATE BY DESIGN
- **Rules decide, AI only explains.** Check-in replies never go to the AI.
- **Fails safe.** "Okay, but my leg hurts" counts as help; unclear replies keep the timer running.
- **Explains itself:** every alert lists why it fired and what else it could be.
- **What leaves the browser:** camera video stays in the browser → **33 landmarks** (x, y, visibility, 15/s) → Kawan hub (same PC by default). No video or images are sent or stored; the hub keeps only events and summaries. **One opt-in exception:** "Check my medicine" sends a single photo to Claude when tapped (needs an AI key).

## 06 · OFFLINE & ONLINE
- **Works without internet:** pose detection, fall & inactivity rules · check-ins by button and chat · spoken prompts (device voices) · reminders, vitals, daily check-in · 104-topic health library · dashboard & report (on the hub PC).
- **Needs internet:** voice input (browser speech service) · Telegram alerts to phones · Claude AI answers & pill check (optional, API key) · phones & remote caregivers (secure link).

## 07 · RESULTS *(Technical execution · Usability)*
**Preliminary test · fall detector on recorded clips [5]**
- **27 / 30 fall clips detected (90%).** The earlier frame-size rule: 17/30.
- **12 / 40 everyday clips triggered a check-in**; 10 of them show people lying down on purpose.
- A check-in asks the person → "I'm okay" = low-priority note → phones alerted only on "help" or no reply.
- *Test conditions:* UR Fall dataset, 70 lab clips of actors, one room, side-view camera; same pose model and settings as the app; each clip's last frame held 10 s (person stays down).
- **Not real-world accuracy.** Preliminary lab testing; not clinically validated.

**148 automated tests:** 117 backend · 19 frontend · 12 browser end-to-end, run by GitHub Actions on every push.

**Early informal feedback · 4 testers (3 friends and a parent)**
- "The reminders are the part I'd use every day."
- "I don't need to read anything. I just talk to it and it talks back."
- "It noticed when I fell and asked if I was okay."
- "I asked what ibuprofen is and finally understood it."

| What we heard | What we did / will do |
|---|---|
| Alerts on 2–3 caregivers' phones | ✓ Done: Telegram to every caregiver |
| Voice sometimes misses words | Tap buttons as backup; better speech next |
| Knows less than chatbots | Deliberate: cited sources only |

## 08 · FEASIBILITY & NEXT STEPS *(Feasibility)*
- **Ready to run today:** a laptop or tablet with a webcam + Chrome/Edge · free open-source stack; AI and Telegram optional · one command; a secure link for phones.
- **Roadmap:** NOW working prototype, tried by 4 early users · NEXT caregiver login, hosted multi-household version, push alerts, device integration · LATER clinical validation with healthcare partners, more emergency types.

## FOOTER
- QR: Demo video → https://drive.google.com/drive/folders/1YvF9wa3N2mt3SOXe9MK3IwnZqf-68v54?usp=sharing
- QR: Source code → https://github.com/MA35STRO/Nexora-Healthtech-and-Community-Wellness
- **Prototype — not a medical device. In an emergency call 999.** One camera, one person in view. Health library from MOH Malaysia CPGs, WHO and NHS. Built with help from Claude Code (AI coding assistant), as the rules require us to disclose.

## REFERENCES
1. IPH, MOH Malaysia. *NHMS 2023: NCD Fact Sheet.* 2024.
2. WHO. *Falls — Fact sheet.* 2021.
3. Fleming J, Brayne C. Inability to get up after falling, subsequent time on floor, and summoning help: prospective cohort study in people over 90. *BMJ* 2008;337:a2227.
4. WHO. *Adherence to Long-Term Therapies: Evidence for Action.* 2003.
5. Kwolek B, Kepski M. Human fall detection on embedded platform using depth maps and wireless accelerometer. *Comput Methods Programs Biomed* 2014;117(3):489–501. UR Fall Detection Dataset, CC BY-NC-SA 4.0.
6. Google. *MediaPipe Pose Landmarker.*

---

## Verified facts (where each claim comes from)
| Claim | Source in repo |
|---|---|
| Browser sends 33 landmarks `[x, y, visibility]` (4 dp) + motion, ~15/s, no images | `frontend/src/camera/useCamera.ts` (FPS = 15, `ws.send({lm, motion})`), `poseMath.ts` `pack()`, `backend/app/main.py` `ws_perception` |
| Hub binds to 127.0.0.1 (same PC) by default | `start.ps1`, `start.sh`, `tunnel.ps1` |
| Hub stores events/records, never landmarks or images | `backend/app/database.py` schema, `hub.py` `_record` / `add_record` |
| Pill check sends one JPEG only on tap, needs AI key | `Companion.tsx` `pillCheck` → `/api/pillcheck` → `hub.pill_check` → `ai_answers.read_medicine` |
| Pose model & WASM served locally (CDN only as fallback) | `useCamera.ts` `LOCAL_MODEL` / `CDN_MODEL`, `frontend/public/mediapipe` |
| Voice input = browser Web Speech API (online service in Chrome/Edge) | `frontend/src/voice/useVoice.ts` |
| Check-in does not alert phones; Telegram only on escalation or caregiver notice | `safety_engine.py` (`checkin_sent`, `user_ok`, `escalated`), `hub.py` `_record` |
| 27/30, 12/40, 17/30, test conditions | `backend/eval/RESULTS.md` |
| 117 / 19 / 12 tests | pytest, vitest and Playwright runs on 2026-11-11 |
