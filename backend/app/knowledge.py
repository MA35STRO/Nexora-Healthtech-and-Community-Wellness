"""Offline health-literacy knowledge base: curated EN/BM explanations + simple keyword retrieval.

Used when there is no API key / no internet, and as grounding context for the LLM.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

PATH = Path(__file__).parent / "data" / "knowledge.json"


@lru_cache
def topics() -> list[dict]:
    return json.loads(PATH.read_text(encoding="utf-8"))


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", s.lower()))


def search(text: str, k: int = 1) -> list[tuple[float, dict]]:
    t = " " + " ".join(re.findall(r"[a-z0-9']+", text.lower())) + " "
    words = _words(text)
    scored = []
    for topic in topics():
        score = 0.0
        for kw in topic["keywords"]:
            norm = " ".join(re.findall(r"[a-z0-9']+", kw.lower()))
            if f" {norm} " in t:
                score += 1 + len(norm.split())   # multi-word phrase matches count more
        score += 0.5 * len(words & (_words(topic["title"]) - {"and", "a", "the", "with", "at", "of"}))
        if score:
            scored.append((score, topic))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def answer(text: str, lang: str = "en") -> Optional[dict]:
    hits = search(text)
    if not hits or hits[0][0] < 1:
        return None
    topic = hits[0][1]
    return {"id": topic["id"], "title": topic["title"], "text": topic["ms" if lang == "ms" else "en"]}


FALLBACK = {
    "en": "I don't have offline information about that yet. Your pharmacist or doctor is the best person to ask — "
          "and with an internet connection I can explain more. If you feel unwell right now, tell me and I'll alert your caregiver.",
    "ms": "Saya belum ada maklumat luar talian tentang itu. Ahli farmasi atau doktor anda paling sesuai untuk ditanya — "
          "dan dengan sambungan internet saya boleh terangkan lebih lanjut. Jika anda rasa tidak sihat sekarang, beritahu saya.",
}
