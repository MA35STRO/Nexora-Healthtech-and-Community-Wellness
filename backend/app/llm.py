"""Optional Claude integration for friendly, plain-language explanations.

The LLM NEVER decides anything safety-related: falls, check-ins, escalation, red flags and medication
state are all handled by deterministic code before a message ever gets here. If there is no API key,
no internet, or any error, we fall back to the offline knowledge base.
"""
import json
import logging
import re
from typing import Optional

from . import knowledge
from .config import Settings, settings as default_settings

log = logging.getLogger("baymax.llm")

SYSTEM = """You are Kawan, a warm, patient home health companion for {name}, who lives alone in Malaysia \
and may be elderly, unwell or recovering. Your caregiver contact is {caregiver}.

How you speak:
- Reply in {lang_name}. Use simple everyday words, short sentences, no jargon (explain any medical word you use).
- Keep replies under 90 words: they are read aloud. No markdown, no bullet symbols, no emojis.
- Be kind and encouraging, never alarming or preachy.

What you must and must not do:
- You are NOT a doctor. Never diagnose, never say what condition someone has, never change, start or stop \
medicines or doses. For anything personal, suggest asking their doctor or pharmacist.
- You give general health literacy: what a condition or medicine is, why habits matter, how to use devices.
- If the person describes emergency warning signs (chest pain, breathing difficulty, stroke signs, fainting, \
heavy bleeding, thoughts of self-harm), tell them to call 999 now. Safety systems have already alerted the caregiver.
- Use Malaysian context where useful (999 for emergencies, Talian HEAL 15555 for emotional support, local foods).

Context about {name} (from their app, may be incomplete):
{context}

Trusted reference notes you may use (prefer these facts):
{notes}"""

VISION_PROMPT = """Read the medicine packaging or label in this photo. Reply with ONLY a JSON object:
{{"medicine": "<name or null>", "strength": "<e.g. 500 mg or null>", "matches": "<one of {names} or null>",
"confidence": "high|medium|low", "note": "<one short sentence for the patient, in {lang_name}>"}}
If you can't read a label, set medicine to null and say so in note. Do not give dosing advice."""


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

    def answer(self, text: str, lang: str, context: str, history: list[dict]) -> tuple[str, str]:
        """Returns (reply, source) where source is 'claude' or 'offline'."""
        offline = knowledge.answer(text, lang)
        if self.client is not None:
            try:
                notes = "\n".join(f"- {t['title']}: {t['en']}" for _, t in knowledge.search(text, k=2)) or "(none)"
                msgs = [{"role": "user" if m["from"] == "user" else "assistant", "content": m["text"]}
                        for m in history[-6:] if m.get("text")]
                msgs = _alternate(msgs + [{"role": "user", "content": text}])
                resp = self.client.messages.create(
                    model=self.cfg.anthropic_model, max_tokens=400,
                    system=SYSTEM.format(name=self.cfg.user_name, caregiver=self.cfg.caregiver_name,
                                         lang_name="Bahasa Melayu" if lang == "ms" else "English",
                                         context=context, notes=notes),
                    messages=msgs)
                reply = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
                if reply:
                    return reply, "claude"
            except Exception as e:
                log.warning("Claude call failed, using offline knowledge: %s", e)
        if offline:
            return offline["text"], "offline"
        return knowledge.FALLBACK["ms" if lang == "ms" else "en"], "offline"

    def read_medicine(self, image_b64: str, med_names: list[str], lang: str) -> dict:
        if self.client is None:
            return {"medicine": None, "matches": None, "confidence": "low", "source": "offline",
                    "note": "Pill check needs an internet connection and an API key. Please confirm your medicine "
                            "against the list on screen." if lang != "ms" else
                            "Semakan ubat memerlukan internet dan kunci API. Sila sahkan ubat anda dengan senarai di skrin."}
        try:
            resp = self.client.messages.create(
                model=self.cfg.anthropic_model, max_tokens=300,
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
            return {"medicine": data.get("medicine"), "strength": data.get("strength"), "matches": data.get("matches"),
                    "confidence": data.get("confidence", "low"), "note": data.get("note", ""), "source": "claude"}
        except Exception as e:
            log.warning("Pill check failed: %s", e)
            return {"medicine": None, "matches": None, "confidence": "low", "source": "error",
                    "note": "I couldn't read that. Please try again with the label facing the camera, in good light."}


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
