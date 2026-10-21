"""Deterministic assistant: check-in wording (EN/BM), reply classification and chat routing.

Safety principle: only an *explicit* "I'm okay" clears a check-in. Anything that mentions
help/pain/negation escalates; anything ambiguous stays pending so the timeout still runs.
The AI (ai_answers.py) only explains things — it never makes any of these decisions.
"""

import re
from typing import Literal

Lang = Literal["en", "ms"]
Intent = Literal["ok", "help", "unclear"]
Route = Literal[
    "checkin_reply", "help", "red_flag", "med_taken", "med_snooze", "med_schedule", "wellness", "ask"
]

CHECKIN = {
    "possible_fall": {
        "en": 'I noticed what may have been a fall. Are you okay? Reply "I\'m okay" or "Help".',
        "ms": 'Saya perasan anda mungkin terjatuh. Anda okay? Balas "Saya okay" atau "Tolong".',
    },
    "inactivity": {
        "en": 'I haven\'t seen you move for a while. Are you okay? Reply "I\'m okay" or "Help".',
        "ms": 'Saya tidak nampak anda bergerak untuk seketika. Anda okay? Balas "Saya okay" atau "Tolong".',
    },
    "vitals_alert": {
        "en": 'Your readings look unusual. How are you feeling? Reply "I\'m okay" or "Help".',
        "ms": 'Bacaan kesihatan anda kelihatan luar biasa. Anda rasa okay? Balas "Saya okay" atau "Tolong".',
    },
}
MED_REMINDER = {
    "en": 'It\'s time for your {name} ({dose}). {instructions} Say "I took my medicine" when done.',
    "ms": 'Sudah tiba masa untuk {name} ({dose}). {instructions} Katakan "Saya sudah makan ubat" selepas itu.',
}
REPLIES = {
    "ok": {
        "en": "Thank you for letting me know. I've noted it for your caregiver. Tell me if anything changes.",
        "ms": "Terima kasih kerana memberitahu. Saya telah maklumkan kepada penjaga anda. Beritahu saya jika ada perubahan.",
    },
    "help": {
        "en": "I'm alerting your caregiver now. Stay where you are if you can; help is being requested.",
        "ms": "Saya sedang menghubungi penjaga anda sekarang. Kekal di tempat anda jika boleh; bantuan sedang diminta.",
    },
    "unclear": {
        "en": 'I\'m not sure I understood. Are you okay? Please reply "I\'m okay" or "Help".',
        "ms": 'Maaf, saya kurang faham. Anda okay? Sila balas "Saya okay" atau "Tolong".',
    },
    "idle": {
        "en": "I'm here. I can't give medical advice, but I can contact your caregiver if you need help.",
        "ms": "Saya di sini. Saya tidak boleh memberi nasihat perubatan, tetapi boleh menghubungi penjaga anda jika perlu.",
    },
    "red_flag": {
        "en": "These can be signs of an emergency. Please call 999 now if you can. I'm alerting your caregiver immediately.",
        "ms": "Ini mungkin tanda kecemasan. Sila hubungi 999 sekarang jika boleh. Saya sedang memaklumkan penjaga anda.",
    },
    "med_none": {
        "en": "You have no medicine due right now. Well done staying on track!",
        "ms": "Tiada ubat yang perlu diambil sekarang. Syabas kerana konsisten!",
    },
}

HELP_PATTERNS = [
    r"\bhelp\b",
    r"\btolong\b",
    r"\bbantu",
    r"\bsakit\b",
    r"\bhurt",
    r"\bpain\b",
    r"\binjur",
    r"\bcan'?t (get|stand|move)",
    r"\bcannot (get|stand|move)",
    r"\btak (boleh|dapat) (bangun|bergerak)",
    r"\bemergency\b",
    r"\bkecemasan\b",
    r"\bambulan",
    r"\bambulance\b",
    r"\bdizzy\b",
    r"\bpening\b",
    r"\bbleed",
    r"\bberdarah\b",
    r"\bnot (ok|okay|fine|good|alright)\b",
    r"\b(tak|tidak|x) (ok|okay|baik|sihat)\b",
]
OK_PATTERNS = [
    r"\b(ok|okay|fine|alright)\b",
    r"\bsaya (ok|okay|baik|sihat)\b",
    r"\bno (need|help needed)\b",
    r"\btak apa\b",
    r"\btiada apa\b",
    r"\bjangan risau\b",
    r"^ya$",
    r"^yes$",
]
# Explicit calls for help: always escalate, even when phrased like a question ("can you call help?")
STRONG_HELP = [
    r"\bhelp\b",
    r"\btolong\b",
    r"\bemergency\b",
    r"\bkecemasan\b",
    r"\bambulan",
    r"\bambulance\b",
    r"\bcan'?t (get up|stand|move|breathe)",
    r"\bcannot (get up|stand|move|breathe)",
    r"\btak (boleh|dapat) (bangun|bergerak|bernafas)",
    r"\bi (have )?fell\b",
    r"\bi fall\b",
    r"\bjatuh\b",
    r"\bcall (my )?(son|daughter|caregiver|family|someone)\b",
]
# ...unless "help" clearly means "explain" ("can you help me understand my blood test?")
HELP_EXPLAIN = r"\bhelp (me )?(to )?(understand|explain|learn|know|remember|read)\b|\bbantu (saya )?faham"
QUESTION_START = (
    r"^(what|why|how|when|which|who|is|are|can|could|should|does|do|will|tell me|explain|"
    r"apa|apakah|kenapa|mengapa|bagaimana|bila|bolehkah|adakah|terangkan|ceritakan)\b"
)
MED_TAKEN = [
    r"\b(took|taken|have taken|had) (my |the )?(medicine|medication|meds|pills?|tablets?|dose)\b",
    r"\b(sudah|dah|telah) (makan|ambil|telan) ubat\b",
    r"\bdone (with )?(my )?(medicine|meds|pills?)\b",
]
MED_SNOOZE = [r"\b(later|snooze|remind me later|not now)\b", r"\b(nanti|kemudian)\b"]
MED_SCHEDULE = [
    r"\b(my|next) (medicine|medication|meds|pills?|dose)\b.*\?",
    r"\bwhen (is|do i take)\b.*(medicine|meds|pill|dose)",
    r"\bjadual ubat\b",
    r"\bubat (saya|seterusnya)\b",
]
WELLNESS = [r"\b(daily )?check.?in\b", r"\bhow am i doing\b", r"\bsemakan harian\b"]


def _any(patterns, t):
    return any(re.search(p, t) for p in patterns)


def classify(text: str) -> Intent:
    t = text.lower().strip()
    if _any(HELP_PATTERNS, t):  # help always wins over ok
        return "help"
    if _any(OK_PATTERNS, t):
        return "ok"
    return "unclear"


def is_question(text: str) -> bool:
    t = text.lower().strip()
    return t.endswith("?") or bool(re.search(QUESTION_START, t))


def route(text: str, in_checkin: bool, has_red_flag: bool) -> Route:
    """Decide what kind of message this is. Order matters: safety first, LLM last."""
    t = text.lower().strip()
    if in_checkin:
        return "checkin_reply"  # only the deterministic classifier may answer a check-in
    if _any(STRONG_HELP, t) and not re.search(HELP_EXPLAIN, t):
        return "help"
    if has_red_flag and not is_question(t):
        return "red_flag"  # "I have chest pain" — but not "what causes chest pain?"
    if _any(MED_TAKEN, t):
        return "med_taken"
    if _any(MED_SCHEDULE, t):
        return "med_schedule"
    if _any(MED_SNOOZE, t) and len(t) < 30:
        return "med_snooze"
    if _any(WELLNESS, t) and len(t) < 40:
        return "wellness"
    if classify(t) == "help" and not is_question(t) and not re.search(HELP_EXPLAIN, t):
        return "help"  # "my leg hurts", "saya pening" → caregiver
    return "ask"


def detect_lang(text: str) -> Lang:
    ms_words = {
        "saya",
        "tolong",
        "tak",
        "tidak",
        "baik",
        "sakit",
        "bangun",
        "ya",
        "boleh",
        "apa",
        "ubat",
        "kenapa",
        "bagaimana",
        "sudah",
        "dah",
        "makan",
        "anda",
        "nak",
        "macam",
        "mana",
        "itu",
        "ini",
    }
    return "ms" if set(re.findall(r"[a-z']+", text.lower())) & ms_words else "en"


def wants_lang(text: str, current: Lang) -> Lang:
    """Language follows the user, but very short neutral replies ('ok') keep the current one."""
    words = re.findall(r"[a-z']+", text.lower())
    if len(words) <= 1 and words and words[0] in {"ok", "okay", "yes", "no"}:
        return current
    return detect_lang(text)
