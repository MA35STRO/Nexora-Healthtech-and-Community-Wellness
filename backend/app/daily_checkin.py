"""Daily wellness check-in + red-flag symptom screening (EN/BM).

This is NOT diagnosis. It sorts what the user reports into "what kind of help to seek":
  emergency  → red-flag warning signs: call 999 now, caregiver alerted immediately
  urgent     → see a doctor / clinic today
  routine    → mention it at your next appointment or see a clinic within a few days
  self_care  → nothing worrying reported; keep up healthy habits
Rules are explicit and listed below so caregivers and judges can audit them.
"""

import re
from typing import Optional

# (label shown to people, patterns EN + BM). First-person reports of these → emergency.
RED_FLAGS: list[tuple[str, list[str]]] = [
    (
        "Chest pain or pressure",
        [
            r"chest (pain|tight|pressure|hurts?)",
            r"pain in (my )?chest",
            r"sakit dada",
            r"dada (sakit|sesak|ketat)",
        ],
    ),
    (
        "Difficulty breathing",
        [
            r"(can'?t|cannot|hard to|difficult(y)? (to )?|trouble) breath",
            r"short(ness)? of breath",
            r"breathless",
            r"sesak nafas",
            r"susah (nak )?bernafas",
            r"tak (boleh|dapat) bernafas",
        ],
    ),
    (
        "Face drooping (possible stroke sign)",
        [r"face (is )?droop", r"drooping face", r"muka (senget|herot|jatuh)", r"mulut senget"],
    ),
    (
        "Arm or leg weakness on one side (possible stroke sign)",
        [
            r"(arm|leg|side) (is )?(weak|numb)",
            r"(weak|numb)(ness)? (in|on) (my )?(one )?(arm|leg|side)",
            r"can'?t (lift|move) (my )?(arm|leg)",
            r"(tangan|kaki) (lemah|kebas)",
            r"lemah sebelah",
        ],
    ),
    (
        "Slurred or confused speech (possible stroke sign)",
        [r"slurr", r"can'?t (speak|talk) (properly|clearly)", r"pelat", r"cakap (tak jelas|pelik)"],
    ),
    ("Fainting or collapse", [r"faint", r"passed out", r"black(ed)? out", r"pengsan", r"pitam"]),
    (
        "Severe bleeding",
        [
            r"(heavy|severe|lot of|won'?t stop) bleed",
            r"bleeding (a lot|heavily|won'?t stop)",
            r"berdarah (banyak|teruk)",
            r"darah tak berhenti",
        ],
    ),
    (
        "Sudden severe headache",
        [r"(worst|sudden|severe|extreme) headache", r"sakit kepala (teruk|sangat|tiba)"],
    ),
    ("Sudden confusion", [r"(sudden(ly)?|very) confus", r"keliru"]),
    (
        "Low blood sugar symptoms (shaking, sweating, confusion)",
        [
            r"(shaking|shaky|trembling).*(sweat)",
            r"(sweat).*(shaking|shaky|trembling)",
            r"(gula|sugar) (rendah|low|drop)",
            r"hypo\b",
            r"menggigil.*berpeluh",
        ],
    ),
    (
        "Thoughts of self-harm",
        [r"(kill|hurt|harm) myself", r"suicid", r"(want|wish) to die", r"bunuh diri", r"nak mati"],
    ),
]

SYMPTOM_CHOICES = [
    {"id": "chest_pain", "en": "Chest pain", "ms": "Sakit dada", "red_flag": True},
    {"id": "breathless", "en": "Short of breath", "ms": "Sesak nafas", "red_flag": True},
    {"id": "face_droop", "en": "Face drooping", "ms": "Muka senget", "red_flag": True},
    {"id": "arm_weak", "en": "Arm/leg weakness", "ms": "Tangan/kaki lemah", "red_flag": True},
    {"id": "speech", "en": "Slurred speech", "ms": "Percakapan pelat", "red_flag": True},
    {"id": "fainted", "en": "Fainted", "ms": "Pengsan", "red_flag": True},
    {"id": "dizzy", "en": "Dizziness", "ms": "Pening", "red_flag": False},
    {"id": "headache", "en": "Headache", "ms": "Sakit kepala", "red_flag": False},
    {"id": "fever", "en": "Fever", "ms": "Demam", "red_flag": False},
    {"id": "cough", "en": "Cough", "ms": "Batuk", "red_flag": False},
    {"id": "nausea", "en": "Nausea", "ms": "Loya", "red_flag": False},
    {"id": "swelling", "en": "Leg swelling", "ms": "Kaki bengkak", "red_flag": False},
    {
        "id": "thirst",
        "en": "Very thirsty / peeing a lot",
        "ms": "Sangat dahaga / kerap kencing",
        "red_flag": False,
    },
    {"id": "tired", "en": "Unusually tired", "ms": "Sangat letih", "red_flag": False},
    {"id": "poor_sleep", "en": "Poor sleep", "ms": "Tidur tidak lena", "red_flag": False},
]
_RED_IDS = {"chest_pain": 0, "breathless": 1, "face_droop": 2, "arm_weak": 3, "speech": 4, "fainted": 5}
_URGENT = {"fever", "swelling"}

HOTLINES = {
    "emergency": "999",
    "mental_health": "Talian HEAL 15555",
    "befrienders": "Befrienders KL 03-7627 2929",
}


def red_flags(text: str) -> list[str]:
    t = text.lower()
    return [label for label, pats in RED_FLAGS if any(re.search(p, t) for p in pats)]


def triage(
    mood: Optional[int],
    pain: Optional[int],
    sleep_h: Optional[float],
    symptoms: list[str],
    note: str = "",
    lang: str = "en",
) -> dict:
    """Deterministic, explainable guidance level for a daily check-in."""
    ms = lang == "ms"
    flags = [RED_FLAGS[_RED_IDS[s]][0] for s in symptoms if s in _RED_IDS] + red_flags(note)
    flags = list(dict.fromkeys(flags))
    reasons: list[str] = []
    advice: list[str] = []

    if flags:
        level = "emergency"
        reasons += flags
        if any("self-harm" in f for f in flags):
            advice.append(
                "Sila hubungi Talian HEAL 15555 atau 999 sekarang. Anda tidak keseorangan."
                if ms
                else "Please call Talian HEAL 15555 or 999 now. You are not alone."
            )
        else:
            advice.append(
                "Hubungi 999 sekarang. Jangan memandu sendiri ke hospital."
                if ms
                else "Call 999 now. Do not drive yourself to hospital."
            )
        if any("stroke" in f for f in flags):
            advice.append(
                "Catat masa simptom bermula — doktor perlu tahu."
                if ms
                else "Note the time symptoms started — doctors will need it."
            )
    else:
        urgent = [s for s in symptoms if s in _URGENT]
        if pain is not None and pain >= 8:
            reasons.append(f"Severe pain reported ({pain}/10)")
        if urgent:
            reasons += [next(c["en"] for c in SYMPTOM_CHOICES if c["id"] == s) for s in urgent]
        if reasons:
            level = "urgent"
            advice.append(
                "Sila jumpa doktor atau klinik hari ini." if ms else "Please see a doctor or clinic today."
            )
        else:
            others = [s for s in symptoms if s not in _RED_IDS]
            if others or (pain is not None and pain >= 4):
                level = "routine"
                if others:
                    reasons.append(
                        "Symptoms reported: "
                        + ", ".join(
                            next((c["en"] for c in SYMPTOM_CHOICES if c["id"] == s), s) for s in others
                        )
                    )
                if pain is not None and pain >= 4:
                    reasons.append(f"Moderate pain ({pain}/10)")
                advice.append(
                    "Pantau simptom. Jika berterusan lebih 2–3 hari atau bertambah teruk, jumpa klinik."
                    if ms
                    else "Keep an eye on it. If it lasts more than 2–3 days or gets worse, visit a clinic."
                )
            else:
                level = "self_care"
                advice.append(
                    "Tiada tanda membimbangkan dilaporkan. Teruskan minum air dan bergerak sedikit."
                    if ms
                    else "Nothing worrying reported. Keep drinking water and moving a little."
                )
    if mood is not None and mood <= 2:
        reasons.append(f"Low mood ({mood}/5)")
        advice.append(
            "Mahu saya maklumkan keluarga anda untuk berbual? Talian HEAL 15555 juga sedia membantu."
            if ms
            else "Would you like me to let your family know you'd like a chat? Talian HEAL 15555 is also there to listen."
        )
    if sleep_h is not None and sleep_h < 5:
        reasons.append(f"Short sleep ({sleep_h} h)")
        advice.append("Cuba rehat sebentar hari ini." if ms else "Try to rest a little today.")
    return {
        "level": level,
        "reasons": reasons,
        "advice": advice,
        "red_flags": flags,
        "disclaimer": "Guidance only, not a diagnosis. If in doubt, call 999 or see a doctor.",
    }
