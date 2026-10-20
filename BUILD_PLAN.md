# BAYMAX — Build Plan (UTP CodeFest 2026 HealthTech)

AI home health & safety companion. Prototype only — not a medical device.

## Architecture

```
 Webcam (OpenCV) ──► Perception (MediaPipe Pose) ──┐
                                                    ├─► Observation stream
 Demo scenarios (synthetic pose features) ─────────┘          │
                                                               ▼
                                         FallDetector (temporal rules, explainable reasons)
                                                               │  "possible_fall"
                                                               ▼
                                         ContextEngine (deterministic state machine)
                         MONITORING ─► CHECK_IN ─► (user OK)  ─► low-severity notice
                                           │──► (user asks help) ─► ESCALATED (critical)
                                           └──► (timeout)       ─► ESCALATED (critical)
                                                               │
                         Assistant (EN/BM messages, keyword response classifier; LLM optional, never decides)
                                                               │
                         SQLite (events, incidents)  ◄─────────┤
                                                               ▼
                         FastAPI REST + WebSocket ─► React dashboard (user view, caregiver view, demo panel)
```

Real and demo data go through the **same** detector → engine → store → dashboard path.
Demo data is tagged `source: "demo"` and shown as SIMULATED.

## Status legend
`[x]` done & tested · `[~]` in progress · `[ ]` not started

## P0 — Must work
- [x] Backend skeleton (FastAPI, config via env, `.env.example`)
- [x] FallDetector: rapid descent + horizontal torso + stays down (temporal), with reasons
- [x] ContextEngine: check-in, response, timeout escalation, acknowledge, resolve
- [x] Response classifier EN/BM (explicit "OK" only clears; ambiguous stays pending)
- [x] SQLite event + incident history
- [x] Demo scenarios through the real pipeline (normal, sit/walk, fall, fall+no response, fall+OK, fall+help)
- [x] Unit tests for detector + engine
- [x] Webcam perception thread + MJPEG feed (localhost only, no frames stored)
- [x] React dashboard: companion view, caregiver dashboard, doctor report, demo panel
- [x] Browser-side camera (MediaPipe JS, auto-start) → landmarks-only WebSocket
- [x] Safety disclaimer visible everywhere
- [x] One-command start scripts + README + CI

## P1 — If time permits
- [x] Simulated sensors (motion, room temp, heart rate) clearly labelled SIMULATED
- [x] BM/EN UI switching
- [x] Voice output (browser speechSynthesis) for check-in prompts
- [x] Optional LLM for friendly free-text replies (never decides emergencies; works without API key)
- [x] Voice input (Web Speech API)
- [x] Personal activity baseline (e.g., inactivity longer than usual)

## P2 — Stretch
- [ ] IP camera (RTSP) source
- [ ] Inactivity anomaly detection, multiple rooms, analytics, auth, cloud

## 7-day schedule
| Day | Focus |
|-----|-------|
| 1 | Plan, backend core (detector, engine, store, API, demo), tests |
| 2 | Webcam perception + MJPEG; frontend skeleton wired to WebSocket |
| 3 | Full dashboard (caregiver + user check-in), end-to-end demo works |
| 4 | P1: simulated sensors, BM/EN, voice output, optional LLM |
| 5 | Tune detector on real recordings; robustness; edge cases |
| 6 | Polish UI, README, architecture diagram, pitch draft |
| 7 | Integration, bug fixing, demo rehearsal (no new features) |

## Progress log
- **Day 1:** Backend core done. 35 tests pass (detector, classifier, engine, end-to-end demo→escalation→resolve via
  HTTP/WebSocket). Webcam verified live at ~10–15 fps through the server. Fixed: guessed landmarks when only upper
  body is visible are now ignored (`full_body`).

- **Day 2:** Moved perception to the browser (camera auto-starts, video never leaves the device). Added meds
  scheduler, learned inactivity, simulated vitals + device API, wellness triage with EN/BM red flags, Claude with
  offline knowledge-base fallback, pill-label check, Telegram alerts, voice + "Hey Kawan", Kawan mascot, caregiver
  dashboard with charts, printable doctor report. Tests: 97 pytest, 12 vitest, 8 Playwright e2e (fake webcam).

## Known limitations (be honest with judges)
- Fall detection is heuristic, untested clinically; single-camera, single-person.
- Lying down quickly (e.g. onto a bed) can look like a fall → that's why we check in first.
- Out-of-view falls are only inferred (rapid drop then lost tracking).
