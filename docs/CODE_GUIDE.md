# Code guide — how Kawan works

This is the "start here" document for anyone reading the code (judges, reviewers, new contributors).
It explains the whole system in plain English and points to the exact file and function for every step.

**Contents**
1. [The system in 30 seconds](#1-the-system-in-30-seconds)
2. [Where everything is](#2-where-everything-is)
3. [Walkthrough A — a fall, from camera to caregiver](#3-walkthrough-a--a-fall-from-camera-to-caregiver)
4. [Walkthrough B — asking a health question](#4-walkthrough-b--asking-a-health-question)
5. [Walkthrough C — a medicine reminder](#5-walkthrough-c--a-medicine-reminder)
6. [Key ideas explained](#6-key-ideas-explained)
7. [Design decisions and why](#7-design-decisions-and-why)
8. [How to change common things](#8-how-to-change-common-things)
9. [Tests](#9-tests)

---

## 1. The system in 30 seconds

Kawan has two halves that talk over the local network:

```
 FRONTEND (browser, TypeScript/React)            BACKEND (Python/FastAPI) — "the hub"
 ──────────────────────────────────           ─────────────────────────────────────────
 webcam → MediaPipe finds 33 body points  ──►  pose.py        points → angle, hip height, posture
 (video never leaves the browser)              fall_detector  "was that a fall?"
                                               inactivity     "still for unusually long?"
 buttons / chat / voice  ─────────────────►    conversation   what kind of message is this?
                                               medications    reminder due / dose missed?
 readings form / devices ─────────────────►    vitals         reading dangerous?
                                                      │
                                                      ▼
                                               safety_engine  ask "are you okay?" → escalate
                                                      │
 Companion, Caregiver, Report pages  ◄─────────  hub.snapshot() pushed live over a WebSocket
```

**The golden rule:** every safety decision (fall, check-in, escalation, emergency symptoms, missed medicine)
is made by small, readable, **tested rules** — never by the AI. The AI only *explains* health topics.

---

## 2. Where everything is

### Backend — `backend/app/` (Python)

| File | What it does, in plain English |
|---|---|
| [`main.py`](../backend/app/main.py) | The web server. Lists every URL the app answers (`/api/...`) and the two live connections (`/ws`, `/ws/perception`). Also serves the built website. |
| [`hub.py`](../backend/app/hub.py) | The coordinator. Every input (camera frame, chat message, reading, clock tick) goes through `Hub`, which passes it to the right module and records what happened. |
| [`config.py`](../backend/app/config.py) | Every adjustable number in one place (fall thresholds, check-in timeout, vital-sign limits…), each with a comment. |
| [`data_types.py`](../backend/app/data_types.py) | The shapes of data passed around: `Observation` (one camera frame), `Detection`, `Event` (timeline entry), `Incident` (an alert). |
| [`pose.py`](../backend/app/pose.py) | Turns 33 body points into simple numbers: torso angle, hip height, posture, motion. |
| [`fall_detector.py`](../backend/app/fall_detector.py) | Decides "possible fall" by looking at a short *sequence* of frames, and writes down the reasons. |
| [`inactivity.py`](../backend/app/inactivity.py) | Notices when someone in view hasn't moved for unusually long, learning what's normal for each hour. |
| [`vitals.py`](../backend/app/vitals.py) | Checks readings (heart rate, oxygen, blood pressure, temperature) against safety limits. Also a simulator used only by demo buttons. |
| [`medications.py`](../backend/app/medications.py) | The medicine schedule and clock: when a dose is due, reminded, taken, snoozed or missed. |
| [`daily_checkin.py`](../backend/app/daily_checkin.py) | The daily mood/pain/symptom check-in, and spotting emergency warning signs in what people say (English + Malay). |
| [`safety_engine.py`](../backend/app/safety_engine.py) | **The heart of the safety logic.** Rules R1–R10: open an alert, ask "are you okay?", lower or escalate it, let the caregiver acknowledge/resolve. |
| [`conversation.py`](../backend/app/conversation.py) | Kawan's fixed wording (EN/BM), understanding replies like "I'm okay" / "Tolong", and deciding where a chat message should go. |
| [`ai_answers.py`](../backend/app/ai_answers.py) | Answers health questions: uses Claude (if an API key is set) grounded in the health library, or the library alone offline. Always returns its sources. |
| [`health_library.py`](../backend/app/health_library.py) + [`data/health_library.json`](../backend/app/data/health_library.json) | 71 reviewed health topics in English and Malay, each with its source (MOH Malaysia guidelines, WHO, NHS…), and the search that finds the right one. |
| [`database.py`](../backend/app/database.py) | Saves events, alerts, readings, doses and settings in a small SQLite file. Never stores video. |
| [`telegram_alerts.py`](../backend/app/telegram_alerts.py) | Optional: sends caregiver alerts to a phone via a Telegram bot. |
| [`demo_scenarios.py`](../backend/app/demo_scenarios.py) | The demo buttons: scripted body movements and replies that run through the **real** detectors. |
| [`demo_history.py`](../backend/app/demo_history.py) | Optional, off by default: a week of clearly-labelled SIMULATED history for demos. |

### Frontend — `frontend/src/` (TypeScript + React)

| File | What it does |
|---|---|
| [`pages/Companion.tsx`](../frontend/src/pages/Companion.tsx) | The screen for the person at home: Kawan, big buttons, chat, camera, medicines, readings. |
| [`pages/Caregiver.tsx`](../frontend/src/pages/Caregiver.tsx) | The caregiver dashboard: live status, alert card with reasons, charts, settings, medicine schedule, demo panel. |
| [`pages/Report.tsx`](../frontend/src/pages/Report.tsx) | The printable summary for a doctor's visit. |
| [`pages/Guide.tsx`](../frontend/src/pages/Guide.tsx) | The "How to use" page (EN/BM). |
| [`camera/useCamera.ts`](../frontend/src/camera/useCamera.ts) | Opens the webcam, runs MediaPipe Pose in the browser, draws the skeleton, sends only the 33 points to the hub. |
| [`camera/poseMath.ts`](../frontend/src/camera/poseMath.ts) | Small maths helpers for the camera (packing points, measuring motion). |
| [`voice/useVoice.ts`](../frontend/src/voice/useVoice.ts) + [`voice/wake.ts`](../frontend/src/voice/wake.ts) | Speaking and listening; recognising "Hey Kawan" even when it's misheard. |
| [`api.ts`](../frontend/src/api.ts) | Every call the website makes to the backend, plus the live connection that keeps screens up to date. |
| [`components/`](../frontend/src/components) | Reusable pieces: the Kawan mascot, charts, the check-in pop-up, the readings form, icons. |
| [`i18n.ts`](../frontend/src/i18n.ts) | English and Bahasa Melayu text for the companion screen. |

### Other files

| Path | Purpose |
|---|---|
| `start.ps1` / `start.sh` | One command to install, build and run everything. |
| `tunnel.ps1` | Share the app on phones with a temporary https link. |
| `backend/tests/`, `frontend/src/**/*.test.ts`, `frontend/e2e/` | Automated tests (see [section 9](#9-tests)). |
| `frontend/models/pose_landmarker_lite.task` | Google's MediaPipe pose model (runs in the browser). |
| `frontend/scripts/` | Build helper (copies the pose model for offline use) and the screenshot script. |
| `.github/workflows/ci.yml` | Runs all tests automatically on GitHub for every change. |
| `.env.example` | Optional settings (API key, Telegram, thresholds). Copy to `backend/.env`. |
| `backend/pyproject.toml`, `package.json` → `prettier` | Code-formatting rules so all files look consistent. |

---

## 3. Walkthrough A — a fall, from camera to caregiver

1. **Browser sees the body.** [`useCamera.ts`](../frontend/src/camera/useCamera.ts) opens the webcam and, about 15 times a second, asks MediaPipe for 33 body points. It sends just those numbers (`{"lm": [[x, y, visibility], …], "motion": …}`) over the `/ws/perception` connection. The video itself never leaves the browser.
2. **Server turns points into meaning.** [`main.py`](../backend/app/main.py) → `ws_perception()` hands each frame to `Hub.ingest_points()`, which calls `observation_from_points()` in [`pose.py`](../backend/app/pose.py): torso angle, hip height, posture.
3. **Is this a fall?** `Hub.ingest()` feeds the frame to `FallDetector.update()` in [`fall_detector.py`](../backend/app/fall_detector.py). It only says "possible fall" after a *sequence*: upright → hips drop fast (≥ 20% of the picture in ≤ 1.5 s) → body horizontal or out of view → still down after 2 s. Lying down slowly, sitting down quickly or getting straight back up are ignored.
4. **Ask before alarming.** The `Detection` (with human-readable reasons) goes to `SafetyEngine.on_detection()` in [`safety_engine.py`](../backend/app/safety_engine.py) — rule **R1**: open an alert, start a 20-second timer, and make Kawan ask *"Are you okay?"* (speech bubble + voice).
5. **The person answers (or doesn't).** Their reply goes `Hub.user_message()` → `SafetyEngine.on_user_message()`. `classify()` in [`conversation.py`](../backend/app/conversation.py) decides:
   - "I'm okay" → **R2**: low priority, caregiver just informed.
   - "Help" / "Tolong" / "my leg hurts" → **R3**: escalate now.
   - silence → `SafetyEngine.tick()` (called every 0.5 s) → **R4**: escalate when the timer runs out.
6. **Caregiver is alerted.** Every change is saved by [`database.py`](../backend/app/database.py) and `Hub.snapshot()` is pushed over `/ws` to [`Caregiver.tsx`](../frontend/src/pages/Caregiver.tsx), which turns red, beeps, shows a notification and lists *why*. [`telegram_alerts.py`](../backend/app/telegram_alerts.py) can also message a phone.
7. **Closing the loop.** The caregiver presses Acknowledge / Resolve → `SafetyEngine.acknowledge()` / `resolve()` (**R6**).

## 4. Walkthrough B — asking a health question

1. The user types or says *"What is gliclazide?"* → `Hub.user_message()`.
2. `route()` in [`conversation.py`](../backend/app/conversation.py) checks, **in this order**: is a check-in waiting? → an explicit call for help? → emergency warning signs (`red_flags()` in [`daily_checkin.py`](../backend/app/daily_checkin.py))? → a medicine action? → only then is it treated as a question. So the AI can never "swallow" an emergency.
3. `AIAnswers.answer()` in [`ai_answers.py`](../backend/app/ai_answers.py) searches the [health library](../backend/app/data/health_library.json) for the best-matching topics.
   - **With an API key:** Claude gets those topics (with their sources), the facts the app actually holds about the user (`Hub._context_text()` — missing facts are marked "not entered"), and strict rules: don't invent doses, numbers or personal facts; say "I'm not sure" when unsure. It must report which topics it used; those sources are shown under the answer.
   - **Without a key / offline / on any error:** the best library topic is returned directly, with its source.
4. The answer appears in the chat with "📖 Source: …" underneath, and is spoken aloud if voice is on.

## 5. Walkthrough C — a medicine reminder

1. The caregiver adds a medicine on the Caregiver page → `POST /api/meds` → `MedScheduler.add_med()` in [`medications.py`](../backend/app/medications.py).
2. Every 0.5 s `Hub.tick()` calls `MedScheduler.tick()`. When a dose's time arrives it becomes **due** and Kawan says the reminder; after 10 minutes it reminds again.
3. "I took my medicine" (button, voice or chat) → `MedScheduler.take()` marks it **taken**.
4. If nobody confirms within the grace period (1 hour by default), it becomes **missed** → `SafetyEngine` rule **R9** sends the caregiver a low-priority notice.
5. `adherence()` totals taken/missed doses for the caregiver chart and the doctor report.

---

## 6. Key ideas explained

- **Body points and "visibility".** MediaPipe returns 33 points (x, y between 0 and 1) even for body parts it can't see — it guesses. Each point has a *visibility* score; we only trust frames where shoulders and hips are really visible (`full_body`). This stopped "sitting at the laptop" from being mistaken for standing.
- **Torso angle.** The angle of the shoulder-to-hip line from vertical: 0° = upright, 90° = lying flat.
- **Why look at a sequence, not one frame.** One horizontal frame could just be someone on a sofa. A fall is a *pattern over time*. See the tests in [`test_safety_rules.py`](../backend/tests/test_safety_rules.py) for the cases that must *not* trigger.
- **Check in before alarming.** Cameras make mistakes (lying down fast onto a bed looks like a fall). Asking first keeps false alarms low without missing real ones — silence still escalates.
- **Fail-safe replies.** Only a clear "I'm okay" calms things down. "Okay but my leg hurts" counts as help. Unclear replies keep the timer running.
- **A state machine.** An alert is always in one clear state: `monitoring → check_in → attention (user OK) | escalated (help / no reply)`. Same inputs always give the same result, so it can be tested.
- **Time is passed in.** Rule functions take `now` instead of reading the clock, so tests can "jump" 20 seconds instantly.
- **One lock.** Camera frames, the clock, demos and web requests all arrive at once; `Hub` protects shared state with one lock. The slow AI call happens *outside* the lock so monitoring never pauses.
- **Learning what's normal.** `InactivityMonitor` remembers how long this person usually stays still at each hour (e.g. reading after lunch) and only flags stillness well beyond that, and never during sleeping hours.
- **No made-up data.** A fresh install has no invented person, medicines, readings or history. The AI only sees facts the app actually holds.

## 7. Design decisions and why

| Decision | Why |
|---|---|
| Rules, not a trained AI model, for falls | No labelled data in a hackathon, and caregivers need to see *reasons*. Rules are explainable and testable. |
| The AI never decides emergencies | AI answers vary from run to run; safety logic must be predictable and tested. |
| Camera processing in the browser | Works on any laptop/tablet with no install, and only numbers (not video) reach the server — better privacy. |
| Every health answer shows its source | Trust: judges, users and doctors can check where information comes from. |
| Live updates over a WebSocket | Screens update instantly without constantly re-asking the server. |
| Demo buttons feed the real detectors | The demo proves the actual logic works; it isn't a fake animation. |
| SQLite database | Zero setup, a single file, enough for one household. |

## 8. How to change common things

| I want to… | Change |
|---|---|
| Make fall detection more/less sensitive | `FALL_*` values in [`config.py`](../backend/app/config.py) (or `backend/.env`) |
| Change how long Kawan waits for a reply | `CHECKIN_TIMEOUT_S` in `config.py` |
| Change vital-sign alert limits | `SPO2_LOW`, `HR_HIGH`, `SYS_CRISIS`… in `config.py` |
| Add or edit a health topic | Add an entry (id, title, source, keywords, en, ms) to [`health_library.json`](../backend/app/data/health_library.json) — a test checks every topic has a source and both languages |
| Add an emergency warning phrase | `RED_FLAGS` in [`daily_checkin.py`](../backend/app/daily_checkin.py) |
| Change Kawan's wording | `CHECKIN` / `REPLIES` in [`conversation.py`](../backend/app/conversation.py), screen text in [`i18n.ts`](../frontend/src/i18n.ts) |
| Add a demo button | `SCENARIOS` in [`demo_scenarios.py`](../backend/app/demo_scenarios.py) |

## 9. Tests

| Suite | Command | What it proves |
|---|---|---|
| Backend (104) | `cd backend && .venv/Scripts/python -m pytest -q` | Fall rules, safety engine R1–R10, replies in EN/BM, medicines, inactivity, vitals, triage, AI grounding and citations, no invented data, full API + WebSocket flows |
| Frontend unit (19) | `cd frontend && npm test` | Pose maths, motion score, "Hey Kawan" matching |
| Browser end-to-end (12) | `cd frontend && npx playwright test` | A real Chromium with a fake webcam: camera auto-start, fall → check-in → alert → resolve, medicines, cited answers, triage, settings, readings, guide, report |

| Test file | Covers |
|---|---|
| [`test_safety_rules.py`](../backend/tests/test_safety_rules.py) | Fall detector, reply understanding, safety engine |
| [`test_health_features.py`](../backend/tests/test_health_features.py) | Medicines, inactivity, vitals, daily check-in, chat routing, AI answers, health library, no invented data |
| [`test_demo_scenarios.py`](../backend/tests/test_demo_scenarios.py) | Demo buttons running through the real pipeline |
| [`test_api_end_to_end.py`](../backend/tests/test_api_end_to_end.py) | The web API and live connections, including a fall detected from browser-style body points |
