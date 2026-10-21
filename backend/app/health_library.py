"""Offline health library: curated EN/BM explanations, each with a source, plus the search that finds them.

Used on its own when no AI key is set, and as the trusted reference notes the AI must follow when one is.

How search scores a topic (higher = better match):
  * a keyword phrase appears in the question             → 1 + number of words in the phrase
  * a word is a near-spelling of a keyword ("metfromin")  → 1.5 (typo tolerance)
  * a word appears in the topic title                     → 0.5
  * a word appears in the explanation text                → 0.15 each, at most 0.6
A topic is used as the answer only with a score of 1 or more; weaker matches become "did you mean…" suggestions.
"""

import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Optional

PATH = Path(__file__).parent / "data" / "health_library.json"
ANSWER_SCORE = 1.0
SUGGEST_SCORE = 0.45

STOP = set(
    """a an and the with at of for to do does did what whats when where which who why how is are was were be been
    in on or other you your my i me it its if about can could should would will tell explain know please e g
    this that these those there their have has had get got any some from by as not no yes so too very much many
    apa itu ini ke di dan yang untuk dengan saya awak anda boleh tak tidak ada macam mana bagaimana kenapa
    mengapa bila adakah apakah tolong terangkan ceritakan pasal tentang kalau nak""".split()
)


@lru_cache
def topics() -> list[dict]:
    return json.loads(PATH.read_text(encoding="utf-8"))


def _norm(word: str) -> str:
    """Lower-case and drop a plural 's' so 'tablets' matches 'tablet'."""
    word = word.lower()
    return word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word


def _tokens(text: str) -> list[str]:
    return [_norm(w) for w in re.findall(r"[a-z0-9']+", text.lower())]


@lru_cache
def _index() -> list[tuple[dict, list[str], set[str], set[str], set[str]]]:
    """Pre-computes, per topic: keyword phrases, single-word keywords, title words, body words."""
    out = []
    for t in topics():
        phrases = [" ".join(_tokens(k)) for k in t["keywords"]]
        singles = {p for p in phrases if " " not in p and len(p) >= 5}
        title = set(_tokens(t["title"])) - STOP
        body = {w for w in _tokens(t["en"] + " " + t["ms"]) if len(w) >= 5} - STOP
        out.append((t, phrases, singles, title, body))
    return out


def _similar(a: str, b: str) -> bool:
    return abs(len(a) - len(b)) <= 2 and SequenceMatcher(None, a, b).ratio() >= 0.84


def search(text: str, k: int = 1) -> list[tuple[float, dict]]:
    tokens = _tokens(text)
    padded = f" {' '.join(tokens)} "
    words = set(tokens) - STOP
    scored = []
    for topic, phrases, singles, title, body in _index():
        score = 0.0
        for phrase in phrases:
            if phrase and f" {phrase} " in padded:
                score += 1 + len(phrase.split())  # multi-word phrase matches count more
        for w in words:
            if len(w) >= 5 and w not in singles and any(_similar(w, s) for s in singles):
                score += 1.5  # near-spelling of a keyword (typo)
        score += 0.5 * len(words & title)
        score += min(0.6, 0.15 * len(words & body))
        if score:
            scored.append((round(score, 2), topic))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def answer(text: str, lang: str = "en") -> Optional[dict]:
    """Single best topic, or None when nothing matches well enough."""
    hits = search(text)
    if not hits or hits[0][0] < ANSWER_SCORE:
        return None
    topic = hits[0][1]
    return {"id": topic["id"], "title": topic["title"], "text": topic["ms" if lang == "ms" else "en"]}


def suggestions(text: str, k: int = 3) -> list[dict]:
    """Topics that partly match — offered as "did you mean…?" instead of guessing."""
    return [t for s, t in search(text, k) if SUGGEST_SCORE <= s < ANSWER_SCORE]


FALLBACK = {
    "en": "That topic isn't in my health library yet, so I won't guess. Please ask your pharmacist, doctor or "
    "the nearest Klinik Kesihatan. If you feel unwell right now, press Help and I'll alert your caregiver.",
    "ms": "Topik itu belum ada dalam perpustakaan kesihatan saya, jadi saya tidak akan meneka. Sila tanya ahli "
    "farmasi, doktor atau Klinik Kesihatan berdekatan. Jika anda rasa tidak sihat sekarang, tekan Tolong.",
}
