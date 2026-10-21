"""Optional Claude integration for friendly, plain-language health explanations — grounded and cited.

The LLM NEVER decides anything safety-related: falls, check-ins, escalation, red flags and medication
state are all handled by deterministic code before a message ever gets here.

Accuracy rules:
  * Each question retrieves the best-matching notes from the curated, source-cited knowledge base.
  * Claude must prefer those notes, must not invent numbers/doses/phone numbers/personal facts,
    and must say it is not sure rather than guess.
  * Claude reports which notes it used ("USED: id, id"); the app shows their sources under the answer.
  * No API key / no internet / any error → the offline knowledge base answers (always cited).
"""
import json
import logging
import re
from typing import Optional

from . import knowledge
from .config import Settings, settings as default_settings

log = logging.getLogger("kawan.llm")

SYSTEM = """You are Kawan, a warm, patient home health companion for {name}, who lives at home in Malaysia \
and may be elderly, unwell or recovering. Their caregiver is {caregiver}.

HOW TO SPEAK
- Reply in {lang_name}. Simple everyday words, short sentences. Explain any medical word you use.
- Under 90 words: replies are read aloud. No markdown, bullets or emojis.
- Kind and calm, never alarming or preachy.

ACCURACY — THE MOST IMPORTANT RULES
- Base medical facts on the REFERENCE NOTES below whenever they cover the question. Do not contradict them.
- If the notes don't cover it, you may give only well-established, general health information. If you are not \
confident, say plainly that you're not sure and suggest asking a pharmacist, doctor or the nearest Klinik Kesihatan.
- NEVER invent: statistics, study results, doses or dosing schedules, phone numbers, websites, prices, or anything \
about {name}. Only use personal facts that appear in THEIR APP DATA; if something isn't there, say it isn't recorded.
- Never tell them how much of a medicine to take beyond "follow your prescription or the label"; never suggest \
starting, stopping or changing a medicine.

SAFETY
- You are NOT a doctor: never diagnose or say what condition they have.
- If they describe emergency warning signs (chest pain, breathing difficulty, stroke signs, fainting, heavy \
bleeding, thoughts of self-harm), tell them to call 999 now. The app's safety system has already alerted the caregiver.
- Emotional support line in Malaysia: Talian HEAL 15555. Emergency: 999. Do not give any other numbers.

THEIR APP DATA (entered by them or their caregiver, or measured by the app)
{context}

REFERENCE NOTES (curated, each with an id and source)
{notes}

FINAL LINE: after your reply, add one last line exactly like "USED: <comma-separated note ids you relied on>" \
or "USED: none". This line is removed before the user sees your reply."""

VISION_PROMPT = """Read the medicine packaging or label in this photo. Reply with ONLY a JSON object:
{{"medicine": "<name exactly as printed, or null>", "strength": "<e.g. 500 mg as printed, or null>",
"matches": "<one of {names} if it is clearly the same medicine, else null>",
"confidence": "high|medium|low", "note": "<one short sentence for the patient, in {lang_name}>"}}
Only report text you can actually read. If the label is unclear, set medicine to null and say so in note.
Never guess a medicine from the pill's colour or shape. Do not give dosing advice."""

USED_RE = re.compile(r"\n?\s*USED:\s*(.*)\s*$", re.I)


class Brain:
    def __init__(self, cfg: Settings = default_settings, client=None):
        self.cfg = cfg
        self.client = client
        if client is None and cfg.anthropic_api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=cfg.anthropic_api_key, timeout=cfg.llm_timeout_s,
                                                  max_retries=1)
            except Exception as e:   # SDK missing or bad config → offline mode
                log.warning("Claude unavailable: %s", e)

    @property
    def online(self) -> bool:
        return self.client is not None

    def answer(self, text: str, lang: str, context: str, history: list[dict],
               profile: Optional[dict] = None) -> dict:
        """Returns {"reply", "source": "claude"|"offline", "refs": [{"title", "source"}]}."""
        profile = profile or {}
        hits = [t for score, t in knowledge.search(text, k=3) if score >= 1]
        if self.client is not None:
            try:
                notes = "\n".join(f"[{t['id']}] {t['title']} (source: {t['source']}): {t['en']}" for t in hits) \
                    or "(no matching notes — answer only if it is well-established general information)"
                msgs = [{"role": "user" if m["from"] == "user" else "assistant", "content": m["text"]}
                        for m in history[-6:] if m.get("text")]
                msgs = _alternate(msgs + [{"role": "user", "content": text}])
                resp = self.client.messages.create(
                    model=self.cfg.anthropic_model, max_tokens=450, temperature=0.2,
                    system=SYSTEM.format(name=profile.get("user_name") or "the user",
                                         caregiver=profile.get("caregiver_name") or "their caregiver",
                                         lang_name="Bahasa Melayu" if lang == "ms" else "English",
                                         context=context or "(none)", notes=notes),
                    messages=msgs)
                raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
                reply, used = _split_used(raw)
                if reply:
                    by_id = {t["id"]: t for t in hits}
                    refs = [_ref(by_id[i]) for i in used if i in by_id]
                    return {"reply": reply, "source": "claude", "refs": refs}
            except Exception as e:
                log.warning("Claude call failed, using offline knowledge: %s", e)
        return offline_answer(text, lang)

    def read_medicine(self, image_b64: str, med_names: list[str], lang: str) -> dict:
        if self.client is None:
            return {"medicine": None, "matches": None, "confidence": "low", "source": "offline",
                    "note": "Pill check needs an internet connection and an API key. Please confirm your medicine "
                            "against the list on screen." if lang != "ms" else
                            "Semakan ubat memerlukan internet dan kunci API. Sila sahkan ubat anda dengan senarai di skrin."}
        try:
            resp = self.client.messages.create(
                model=self.cfg.anthropic_model, max_tokens=300, temperature=0,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": VISION_PROMPT.format(names=", ".join(med_names) or "none",
                                                                  lang_name="Bahasa Melayu" if lang == "ms" else "English")},
                ]}])
            raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            m = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(m.group(0)) if m else {}
            if data.get("matches") not in med_names:
                data["matches"] = None
            if data.get("confidence") == "low":
                data["matches"] = None   # never confirm a medicine on a low-confidence read
            return {"medicine": data.get("medicine"), "strength": data.get("strength"), "matches": data.get("matches"),
                    "confidence": data.get("confidence", "low"), "note": data.get("note", ""), "source": "claude"}
        except Exception as e:
            log.warning("Pill check failed: %s", e)
            return {"medicine": None, "matches": None, "confidence": "low", "source": "error",
                    "note": "I couldn't read that. Please try again with the label facing the camera, in good light."}


def offline_answer(text: str, lang: str) -> dict:
    hits = [(s, t) for s, t in knowledge.search(text, k=3) if s >= 1]
    if not hits:
        return {"reply": knowledge.FALLBACK["ms" if lang == "ms" else "en"], "source": "offline", "refs": []}
    best = hits[0][1]
    reply = best["ms" if lang == "ms" else "en"]
    related = [t for s, t in hits[1:] if s >= 0.6 * hits[0][0]]
    if related:
        titles = ", ".join(t["title"] for t in related)
        reply += (f" Saya juga boleh terangkan: {titles}." if lang == "ms" else f" I can also explain: {titles}.")
    return {"reply": reply, "source": "offline", "refs": [_ref(best)]}


def _ref(topic: dict) -> dict:
    return {"title": topic["title"], "source": topic["source"]}


def _split_used(raw: str) -> tuple[str, list[str]]:
    m = USED_RE.search(raw)
    if not m:
        return raw.strip(), []
    ids = [] if m.group(1).strip().lower() == "none" else [i.strip().strip("[]") for i in m.group(1).split(",")]
    return raw[:m.start()].strip(), [i for i in ids if i]


def _alternate(msgs: list[dict]) -> list[dict]:
    """The API needs user/assistant turns to alternate and start with the user."""
    out: list[dict] = []
    for m in msgs:
        if out and out[-1]["role"] == m["role"]:
            out[-1] = {"role": m["role"], "content": out[-1]["content"] + "\n" + m["content"]}
        else:
            out.append(dict(m))
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out
