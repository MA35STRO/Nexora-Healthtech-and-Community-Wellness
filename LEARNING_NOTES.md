# BAYMAX — Learning Notes

Short notes on what you must be able to explain to judges.

## 1. The pipeline (say this in one breath)
Camera → **Perception** (MediaPipe Pose: 33 body landmarks per frame) → **Observation** (torso angle, hip height,
visibility) → **FallDetector** (temporal rules) → **ContextEngine** (state machine) → Store + Dashboard.
Demo mode creates fake *Observations*, not fake alerts, so the demo exercises the real detector and engine.

## 2. Key files
| File | Role | Key function |
|------|------|--------------|
| `backend/app/perception.py` | Landmarks → features | `observation_from_points()` (browser), `pose_features()` |
| `frontend/src/perception/useCamera.ts` | Browser webcam + MediaPipe JS | sends 33 points/frame, never pixels |
| `backend/app/routine.py` | Learned inactivity | `RoutineMonitor.update()`, `threshold()` |
| `backend/app/meds.py` | Medication clock | `MedScheduler.tick()`, `take()` |
| `backend/app/vitals.py` | Vitals rules | `VitalsMonitor._check()` (sustained readings) |
| `backend/app/wellness.py` | Red flags + triage | `red_flags()`, `triage()` |
| `backend/app/llm.py` | Claude, optional | `Brain.answer()` falls back to `knowledge.py` |
| `backend/app/detector.py` | Possible-fall detection | `FallDetector.update()` |
| `backend/app/engine.py` | Safety rules R1–R7 | `on_detection`, `on_user_message`, `tick`, `acknowledge`, `resolve` |
| `backend/app/assistant.py` | EN/BM wording + reply intent | `classify()` |
| `backend/app/hub.py` | Wires everything, thread-safe | `ingest()`, `snapshot()` |
| `backend/app/main.py` | HTTP + WebSocket API | `/api/state`, `/ws`, `/api/video.mjpg` |

## 3. Concepts
- **Pose landmarks & visibility.** MediaPipe outputs x,y in 0–1 for each joint *even when the joint is out of frame* —
  it guesses. `visibility` says how sure it is. We only trust frames where shoulders + hips are visible
  (`full_body`). Found this bug on Day 1: sitting at the laptop was labelled "standing".
- **Torso angle.** `atan2(|dx|, |dy|)` of the shoulder-midpoint → hip-midpoint vector. 0° upright, 90° horizontal.
- **Why temporal detection.** One horizontal frame = could be lying on a sofa. A fall is a *sequence*:
  upright → hip drops ≥20% of frame height within 1.5 s → horizontal (or out of view) → stays down 2 s.
  Slow lying down, sitting quickly, and getting back up are explicitly *not* flagged (see tests).
- **State machine.** States: `monitoring → check_in → attention (user OK) | escalated (help / no reply)`.
  Caregiver acknowledge/resolve closes it. Deterministic = same input always gives same output = testable.
- **Fail-safe classification.** Only an explicit "okay" clears a check-in. "Help" wins over "okay"
  ("okay but my leg hurts" → help). Unclear replies keep the timeout running. Silence escalates.
- **Injected time.** Engine methods take `now` instead of calling the clock → tests can jump 20 s instantly.
- **Threads + one lock.** Camera thread, demo thread, timeout ticker and HTTP requests all touch the same state,
  so `Hub` guards everything with one `RLock`.
- **Privacy.** Frames live only in memory; MJPEG stream is served on 127.0.0.1 only; SQLite stores events, not video.

- **Why the browser runs the camera.** Works on any laptop/tablet with zero install, and privacy is stronger:
  only landmark numbers reach the server. The SAME Python `pose_features()` is reused, so tests still cover it.
- **Chat routing order.** check-in reply → explicit help → red-flag symptoms → medicine intents → LLM. The LLM is
  last, so it can never swallow an emergency.

## 4. Decisions & why
| Decision | Why |
|----------|-----|
| Rules, not an ML classifier, for falls | No labelled data, 7 days, and judges/caregivers need *reasons*. |
| LLM never decides emergencies | LLMs are non-deterministic; safety logic must be testable. |
| Python 3.12 venv via `uv` | MediaPipe wheels lag the newest Python (system has 3.14). |
| WebSocket pushes snapshots | Dashboard updates instantly without polling every endpoint. |
| Same pipeline for demo + camera | The demo proves the real logic, not a mock-up. |

## 5. Honest limitations
Single camera, single person, heuristic thresholds not clinically validated, out-of-view falls only inferred,
a quick lie-down can look like a fall (→ that's why we check in before alerting as critical).

## Exercises
- [ ] **E1** Add a demo scenario `lie_down_slowly` (person lowers onto a bed over ~5 s) in `backend/app/demo.py`.
      Predict: should it raise an alert? Run it and check.
- [ ] **E2** Explain in 2 sentences why `got_up` needs the hip to *rise*, not just the torso to be upright.
