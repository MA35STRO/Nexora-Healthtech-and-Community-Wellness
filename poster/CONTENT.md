# Kawan — A1 poster content (Phase 2 draft)

Source of truth for the poster text. Every number here has a reference or comes from the repo.
`[n]` = reference number.

---

## HEADER
- Logos: UTP · CODEFEST'26 SYNTECH
- **Kawan**
- *An AI guardian for people who live alone — it notices, checks in, and alerts family only when needed.*
- Tagline: **Not a doctor. Not a surveillance camera. A guardian.**
- Team **Nexora** · HealthTech track
- Ajmal Haikal bin Mohd Zakhiruddin · Nik Mohamad Fairuz Addailami bin Mohamed Zabedi · Muhammad Iyad Mustaqim bin Muhd Gaddafi · Muhammad Zulfiqar bin Zuraimi

---

## 1 · THE PROBLEM  *(Impact)*

**Living alone with an illness is risky — and help arrives too late.**

| Stat | Caption |
|---|---|
| **15.6%** | of Malaysian adults have diabetes and **29.2%** have hypertension; about 4 in 10 of them don't know it [1] |
| **684,000** | people die from falls every year; adults over 60 suffer the most fatal falls [2] |
| **80%** | of fallers over 90 could not get up alone; **30%** lay on the floor for an hour or more, and call alarms mostly went unused [3] |
| **~50%** | of patients with long-term illness don't take their medicine as prescribed [4] |

> Today's tools wait for the person to press a button or read a chart. After a fall, in confusion, or when a dose is forgotten, that is exactly when they can't.

---

## 2 · OUR SOLUTION

**Kawan turns the laptop or tablet a person already owns into a caring guardian.**

Core loop (big graphic):
**NOTICE → CHECK IN → ESCALATE only if needed → EXPLAIN WHY**

- Uses the device's own webcam: no wearables, no button to press, no subscription.
- Asks *"Are you okay?"* before raising any alarm, by voice, button or chat, in English or Bahasa Melayu.
- Tells the caregiver **why** it is worried, not just *that* it is.

---

## 3 · HOW IT WORKS  *(Technical Execution)*

Diagram, left → right:

1. **Camera (on the device).** MediaPipe Pose runs in the browser and finds 33 body points per frame. *The video never leaves the device.*
2. **Kawan hub (Python FastAPI).** Detectors turn those points and other inputs into events:
   - Fall detector · Inactivity monitor (learns this person's normal) · Vitals monitor · Medicine scheduler · Daily check-in
3. **Safety engine:** 10 explicit, tested rules (R1–R10) decide what happens:
   - "I'm okay" → low-priority note to the caregiver
   - "Help", or no reply in 20 s → **ESCALATE**
   - Red-flag symptom (e.g. chest pain) → escalate immediately
4. **Caregivers:** live dashboard, Telegram alerts to **every** caregiver's phone, printable doctor report.

Side branch: *Health question → cited 104-topic library (offline), or Claude grounded in that library (optional).*

**Fall detection, step by step** (small inset):
upright → hips drop fast (≥ 0.6 torso lengths in ≤ 1.5 s) → body horizontal or out of view → still down after 2 s.
*Measured in the person's own body size, so it works near or far from the camera.*

---

## 4 · KEY FEATURES  *(Usability)*  — 6 tiles, each with a real screenshot

1. **Fall & inactivity detection**, with reasons and "what else it could be"
2. **Check-in before alarm:** big buttons, voice ("Hey Kawan"), EN / BM
3. **Medicine reminders:** spoken, one-tap "I took it", missed-dose notice, adherence chart
4. **Vitals & daily check-in:** sustained-reading alerts, non-diagnostic triage (self-care → see a doctor → call 999)
5. **Health answers with sources:** 104 topics from MOH Malaysia clinical practice guidelines, WHO and NHS; the source is shown under every answer
6. **Caregiver dashboard:** live status, timeline, charts, alerts to multiple caregivers' phones, one-click doctor report

---

## 5 · SAFETY & PRIVACY BY DESIGN  *(Technical Execution)*

- **Rules decide, AI only explains.** Every safety decision is a tested rule; the AI never sees a check-in reply.
- **Fails safe.** *"Okay, but my leg hurts"* counts as help. Unclear replies keep the timer running.
- **Explains itself.** Every alert lists why it fired and what else it could be.
- **Private.** Only 33 body points leave the camera; no images are stored. Privacy mode shows just a skeleton.
- **Works offline.** Pose model, rules and health library are all local.
- **Honest data.** Nothing is invented; demo data is always labelled SIMULATED.

---

## 6 · RESULTS  *(Technical Execution + Usability)*

**Fall detection on real videos** — UR Fall Detection Dataset [5], 30 falls + 40 everyday activities:
- **27 / 30 real falls caught (90%)**; the earlier frame-size rule caught 17/30
- 13 of 40 everyday clips triggered a check-in, 11 of them people lying down on purpose (why Kawan asks first)
- *Same pose model and settings as the app.*

**Engineering quality**
- **148 automated tests** (117 backend · 19 frontend · 12 browser end-to-end), run on every push by GitHub Actions
- Open source (MIT), with a plain-English code guide

**Early informal feedback** — 4 testers (3 friends and a parent) tried voice check-ins, health questions, the fall detector, calling for help, reminders and the caregiver page:
- *"The reminders are the part I'd use every day."*
- *"I don't need to read anything. I just talk to it and it talks back."*
- *"It noticed when I fell and asked if I was okay. That's reassuring when no one's home."*
- *"I asked what ibuprofen is and how it works, and finally understood it."*

**What we heard → what we did**

| What we heard | What we did / will do |
|---|---|
| 2–3 caregivers want alerts on their phones | ✅ **Done:** Telegram alerts go to every caregiver |
| Voice sometimes doesn't catch what's said | Big tap buttons as a backup now; better speech recognition next |
| It knows less than general chatbots | Deliberate: it answers only from cited sources, so it can't invent medical facts |
| Cover emergencies beyond falls | Already alerts on red-flag symptoms and abnormal vitals; more types planned |

---

## 7 · FEASIBILITY  *(Feasibility)*

**Ready to run today**
- **Hardware:** any laptop or tablet with a webcam, plus Chrome or Edge. Nothing to buy.
- **Cost:** free open-source stack; core features work offline; AI and Telegram are optional.
- **Setup:** one command starts everything; a secure link opens it on phones.
- **Maintainable:** every threshold lives in one config file, and 148 tests guard every change.

**Roadmap**
- **Now — working prototype:** all features above, tested with 4 early users
- **Next:** caregiver login · hosted multi-household version · phone push notifications · smartwatch / oximeter integration · better speech recognition
- **Later:** clinical validation with healthcare partners · more emergency types · dedicated low-cost tablet kiosk

**Honest limitations**
Detection rules are not clinically validated · one camera, one person · the browser tab must stay open · not a medical device.

---

## FOOTER
- QR: **GitHub repo** → https://github.com/MA35STRO/Nexora-Healthtech-and-Community-Wellness
- QR: **Demo video** → https://drive.google.com/drive/folders/1YvF9wa3N2mt3SOXe9MK3IwnZqf-68v54?usp=sharing
- *Prototype for UTP CodeFest '26. Not a medical device. In an emergency call 999.*
- *Built with the help of Claude Code (AI coding assistant), as disclosed under competition rules.*

## REFERENCES
1. Institute for Public Health, Ministry of Health Malaysia. *National Health and Morbidity Survey (NHMS) 2023: Non-Communicable Diseases — Fact Sheet.* 2024. iku.moh.gov.my
2. World Health Organization. *Falls — Fact sheet.* April 2021. who.int/news-room/fact-sheets/detail/falls
3. Fleming J, Brayne C. Inability to get up after falling, subsequent time on floor, and summoning help: prospective cohort study in people over 90. *BMJ* 2008;337:a2227.
4. World Health Organization. *Adherence to Long-Term Therapies: Evidence for Action.* 2003.
5. Kwolek B, Kepski M. Human fall detection on embedded platform using depth maps and wireless accelerometer. *Computer Methods and Programs in Biomedicine* 2014;117(3):489–501. (UR Fall Detection Dataset, CC BY-NC-SA 4.0)
6. Google. *MediaPipe Pose Landmarker.* ai.google.dev/edge/mediapipe
7. Ministry of Health Malaysia. Clinical Practice Guidelines (Type 2 Diabetes 2020, Hypertension 2018, and others), as cited in the app's health library.
