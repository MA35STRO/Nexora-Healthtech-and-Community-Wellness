"""Optional Claude integration for friendly, plain-language health explanations — grounded and cited.

The LLM NEVER decides anything safety-related: falls, check-ins, escalation, red flags and medication
state are all handled by deterministic code before a message ever gets here.

Accuracy rules:
  * Each question retrieves the best-matching notes from the curated, source-cited health library.
  * Claude must prefer those notes, must not invent numbers/doses/phone numbers/personal facts,
    and must say it is not sure rather than guess.
  * Claude reports which notes it used ("USED: id, id"); the app shows their sources under the answer.
  * No API key / no internet / any error → the offline health library answers (always cited).
"""

import json
import logging
import re
from typing import Optional

import httpx

from . import health_library
from .config import Settings
from .config import settings as default_settings

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
- Mention their own medicines only when the question is about medicines. Never say what a medicine is for unless \
the REFERENCE NOTES or THEIR APP DATA say so.
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

# The model only COPIES printed text. It is not told which medicines the person takes (a small model given
# that list "reads" it everywhere, even on a plain pill), and Kawan's own code does the matching.
VISION_PROMPT = """Copy the printed words you can clearly read on the medicine box or label in this photo.
Reply with ONLY a JSON object:
{"text": "<every printed word you can clearly read, exactly as printed>",
 "medicine": "<the medicine name exactly as printed, or null>",
 "strength": "<the strength exactly as printed, e.g. 500 mg, or null>"}
If there is no printed label, or the letters are too blurry to read one by one, reply exactly:
{"text": "", "medicine": null, "strength": null}
Never guess a medicine from a pill's colour or shape, or from the box design. Add nothing else."""

PILL_NOTES = {
    "match": {
        "en": "The label seems to say {name}{strength}, which is on your medicine list. Please still check the "
        "label yourself before taking it.",
        "ms": "Label ini nampaknya menyebut {name}{strength}, yang ada dalam senarai ubat anda. Sila semak label "
        "sendiri sebelum mengambilnya.",
    },
    "other": {
        "en": "I'm not sure, but the label may say {name}{strength}. That is NOT on your medicine list, so check "
        "with your caregiver or pharmacist before taking it.",
        "ms": "Saya tidak pasti, tetapi label mungkin menyebut {name}{strength}. Ia TIADA dalam senarai ubat anda, "
        "jadi tanya penjaga atau ahli farmasi sebelum mengambilnya.",
    },
    "unread": {
        "en": "I couldn't read a medicine name. Hold the box with the printed name facing the camera, in good "
        "light, and try again.",
        "ms": "Saya tidak dapat membaca nama ubat. Pegang kotak dengan nama ubat menghadap kamera, dalam "
        "cahaya terang, dan cuba lagi.",
    },
}


def _in_text(name: str, text: str) -> bool:
    return bool(name) and re.search(rf"\b{re.escape(name.lower())}\b", text.lower()) is not None


def match_label(data: dict, med_names: list[str], lang: str) -> dict:
    """Decide what a label read means, in code: never trust a name the model didn't actually transcribe."""
    text = str(data.get("text") or "").strip()
    medicine = data.get("medicine") or None
    strength = data.get("strength") or None
    if medicine and not _in_text(str(medicine), text):
        medicine = None  # it named a medicine that isn't in the words it read: a guess
    if strength and not _in_text(str(strength), text):
        strength = None
    matches = next((n for n in med_names if _in_text(n, text)), None)
    if matches and not medicine:
        medicine = matches
    key = "match" if matches else "other" if medicine else "unread"
    lang = "ms" if lang == "ms" else "en"
    note = PILL_NOTES[key][lang].format(name=medicine, strength=f" {strength}" if strength else "")
    return {
        "medicine": medicine,
        "strength": strength,
        "matches": matches,
        "confidence": "high" if matches else "medium" if medicine else "low",
        "note": note,
        "read_text": text[:300],
    }


USED_RE = re.compile(r"\n?\s*USED:\s*(.*)\s*$", re.I)
MAX_REPLY_TOKENS = 300  # replies should be under 90 words (~150 tokens) + the USED line
_TAIL_RE = re.compile(r"\n\s*(U|US|USE|USED|USED:.*)$", re.I | re.S)  # the USED line, half-typed


def visible_part(raw: str) -> str:
    """What a half-written reply should show: never the hidden "USED: …" line, even half-typed."""
    m = USED_RE.search(raw)
    if m:
        raw = raw[: m.start()]
    return _TAIL_RE.sub("", raw).strip()


class OllamaChat:
    """A local model served by Ollama on this computer: free, no API key, nothing leaves the machine.

    Talks to Ollama's own HTTP API (/api/chat), so no extra Python package is needed.
    """

    def __init__(self, url: str, model: str, timeout_s: float):
        self.url, self.model, self.timeout_s = url.rstrip("/"), model, timeout_s

    def complete(
        self, system: str, messages: list[dict], max_tokens: int, temperature: float, image_b64: str = ""
    ) -> str:
        msgs = [{"role": "system", "content": system}] if system else []
        msgs += [dict(m) for m in messages]
        if image_b64 and msgs:
            msgs[-1]["images"] = [image_b64]
        r = httpx.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "messages": msgs,
                "stream": False,
                "keep_alive": "30m",  # stay loaded between questions, then free the memory
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=self.timeout_s,
        )
        r.raise_for_status()
        return (r.json().get("message") or {}).get("content", "")

    def stream(self, system: str, messages: list[dict], max_tokens: int, temperature: float):
        """Yield the reply piece by piece as the model writes it, so it can be shown straight away."""
        msgs = [{"role": "system", "content": system}] + [dict(m) for m in messages]
        with httpx.stream(
            "POST",
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "messages": msgs,
                "stream": True,
                "keep_alive": "30m",
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=self.timeout_s,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                part = json.loads(line)
                piece = (part.get("message") or {}).get("content", "")
                if piece:
                    yield piece
                if part.get("done"):
                    break

    def warm_up(self):
        """Load the model into memory so the first question doesn't wait for it."""
        try:
            self.complete("", [{"role": "user", "content": "Hi"}], 1, 0)
        except Exception as e:
            log.info("Local model warm-up skipped: %s", e)


def ollama_models(url: str) -> list[str]:
    """Models installed in Ollama, or [] if Ollama isn't running."""
    try:
        r = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


class AIAnswers:
    def __init__(self, cfg: Settings = default_settings, client=None, local: Optional[OllamaChat] = None):
        self.cfg = cfg
        self.client = client  # Claude (anthropic SDK client)
        self.local = local  # or a local Ollama model; the one in use wins over Claude
        if local is None and client is None and cfg.ollama_model:
            self.local = OllamaChat(cfg.ollama_url, cfg.ollama_model, cfg.ollama_timeout_s)
        if self.local is None and client is None and cfg.anthropic_api_key:
            try:
                import anthropic

                self.client = anthropic.Anthropic(
                    api_key=cfg.anthropic_api_key, timeout=cfg.llm_timeout_s, max_retries=1
                )
            except Exception as e:  # SDK missing or bad config → offline mode
                log.warning("Claude unavailable: %s", e)

    @property
    def online(self) -> bool:
        return self.local is not None or self.client is not None

    @property
    def provider(self) -> Optional[str]:
        return "local" if self.local else "claude" if self.client else None

    @property
    def model(self) -> Optional[str]:
        return self.local.model if self.local else self.cfg.anthropic_model if self.client else None

    def _complete(
        self, system: str, messages: list[dict], max_tokens: int, temperature: float, image_b64: str = ""
    ) -> str:
        if self.local is not None:
            return self.local.complete(system, messages, max_tokens, temperature, image_b64)
        if image_b64:
            text = messages[-1]["content"]
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
                        },
                        {"type": "text", "text": text},
                    ],
                }
            ]
        kwargs = {"system": system} if system else {}
        resp = self.client.messages.create(
            model=self.cfg.anthropic_model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages,
            **kwargs,
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    def check(self) -> tuple[bool, str]:
        """Tiny test call so the caregiver knows straight away whether the connection works."""
        if self.local is not None:
            installed = ollama_models(self.local.url)
            if not installed:
                return False, "Ollama isn't running on this computer. Open the Ollama app and try again."
            if self.local.model not in installed:
                return (
                    False,
                    f"Model '{self.local.model}' isn't installed. Run: ollama pull {self.local.model}",
                )
            try:  # also loads the model into memory, so the first real question is quicker
                self.local.complete("", [{"role": "user", "content": "Hi"}], 1, 0)
                return True, f"Connected to the local model {self.local.model}. Nothing leaves this computer."
            except Exception as e:
                return (
                    False,
                    f"Ollama couldn't run the model ({type(e).__name__}). It may need more free memory.",
                )
        if self.client is None:
            return False, "No API key set."
        try:
            self.client.messages.create(
                model=self.cfg.anthropic_model, max_tokens=5, messages=[{"role": "user", "content": "Hi"}]
            )
            return True, "Connected to Claude."
        except Exception as e:  # map the SDK's errors to plain words
            name = type(e).__name__
            if "Authentication" in name or "PermissionDenied" in name:
                return (
                    False,
                    "The key was not accepted. Check you copied the whole key (it starts with sk-ant-).",
                )
            if "Connection" in name or "Timeout" in name:
                return False, "Couldn't reach Claude. Check this computer's internet connection."
            if "RateLimit" in name:
                return (
                    False,
                    "Claude is busy or the account has no credit left. Check Billing in the Anthropic console.",
                )
            if "NotFound" in name:
                return False, f"The model '{self.cfg.anthropic_model}' isn't available on this account."
            return False, f"Claude returned an error: {name}."

    def answer(
        self,
        text: str,
        lang: str,
        context: str,
        history: list[dict],
        profile: Optional[dict] = None,
        on_partial=None,
    ) -> dict:
        """Returns {"reply", "source": "claude"|"local"|"offline", "refs": [{"title", "source"}]}."""
        profile = profile or {}
        hits = [t for score, t in health_library.search(text, k=3) if score >= 1]
        if self.online:
            try:
                notes = (
                    "\n".join(f"[{t['id']}] {t['title']} (source: {t['source']}): {t['en']}" for t in hits)
                    or "(no matching notes — answer only if it is well-established general information)"
                )
                msgs = [
                    {"role": "user" if m["from"] == "user" else "assistant", "content": m["text"]}
                    for m in history[-6:]
                    if m.get("text")
                ]
                msgs = _alternate(msgs + [{"role": "user", "content": text}])
                system = SYSTEM.format(
                    name=profile.get("user_name") or "the user",
                    caregiver=profile.get("caregiver_name") or "their caregiver",
                    lang_name="Bahasa Melayu" if lang == "ms" else "English",
                    context=context or "(none)",
                    notes=notes,
                )
                if self.local is not None and on_partial is not None:
                    raw = ""
                    for piece in self.local.stream(system, msgs, MAX_REPLY_TOKENS, 0.2):
                        raw += piece
                        shown = visible_part(raw)
                        if shown:
                            on_partial(shown)
                    raw = raw.strip()
                else:
                    raw = self._complete(system, msgs, MAX_REPLY_TOKENS, 0.2).strip()
                reply, used = _split_used(raw)
                if reply:
                    by_id = {t["id"]: t for t in hits}
                    refs = [_ref(by_id[i]) for i in used if i in by_id]
                    return {"reply": reply, "source": self.provider, "refs": refs}
            except Exception as e:
                log.warning("AI call failed, using offline knowledge: %s", e)
        return offline_answer(text, lang)

    def read_medicine(
        self, image_b64: str, med_names: list[str], lang: str, alternates: Optional[list[str]] = None
    ) -> dict:
        """Read the label. If that doesn't find a medicine on their list, try each alternate photo (e.g. the
        same frame un-mirrored) and keep the best read: a match on their list, else any name, else the first."""
        first = self._read_one(image_b64, med_names, lang)
        best = first
        for alt in alternates or []:
            if best["matches"]:
                break
            r = self._read_one(alt, med_names, lang)
            if r["matches"] or (r["medicine"] and not best["medicine"]):
                best = r
        return best

    def _read_one(self, image_b64: str, med_names: list[str], lang: str) -> dict:
        if not self.online:
            return {
                "medicine": None,
                "matches": None,
                "confidence": "low",
                "source": "offline",
                "note": "Pill check needs an AI connection (a local model or Claude). Please confirm your medicine "
                "against the list on screen."
                if lang != "ms"
                else "Semakan ubat memerlukan sambungan AI. Sila sahkan ubat anda dengan senarai di skrin.",
            }
        try:
            raw = self._complete(
                "", [{"role": "user", "content": VISION_PROMPT}], 300, 0, image_b64=image_b64
            )
            m = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(m.group(0)) if m else {}
            return {**match_label(data, med_names, lang), "source": self.provider}
        except Exception as e:
            log.warning("Pill check failed: %s", e)
            return {
                "medicine": None,
                "matches": None,
                "confidence": "low",
                "source": "error",
                "note": "I couldn't read that. Please try again with the label facing the camera, in good light.",
            }


def offline_answer(text: str, lang: str) -> dict:
    hits = [(s, t) for s, t in health_library.search(text, k=3) if s >= health_library.ANSWER_SCORE]
    if not hits:
        maybe = health_library.suggestions(text)
        if maybe:  # partly matched: offer choices rather than guess
            titles = ", ".join(t["title"] for t in maybe)
            reply = (
                f"Saya kurang pasti. Adakah anda maksudkan: {titles}? Tanya semula dengan nama topik itu."
                if lang == "ms"
                else f"I'm not completely sure what you mean. Did you mean: {titles}? Ask me again with that topic."
            )
            return {"reply": reply, "source": "offline", "refs": []}
        return {
            "reply": health_library.FALLBACK["ms" if lang == "ms" else "en"],
            "source": "offline",
            "refs": [],
        }
    best = hits[0][1]
    reply = best["ms" if lang == "ms" else "en"]
    related = [t for s, t in hits[1:] if s >= 0.6 * hits[0][0]]
    if related:
        titles = ", ".join(t["title"] for t in related)
        reply += (
            f" Saya juga boleh terangkan: {titles}." if lang == "ms" else f" I can also explain: {titles}."
        )
    return {"reply": reply, "source": "offline", "refs": [_ref(best)]}


def _ref(topic: dict) -> dict:
    return {"title": topic["title"], "source": topic["source"]}


def _split_used(raw: str) -> tuple[str, list[str]]:
    m = USED_RE.search(raw)
    if not m:
        return raw.strip(), []
    ids = (
        [] if m.group(1).strip().lower() == "none" else [i.strip().strip("[]") for i in m.group(1).split(",")]
    )
    return raw[: m.start()].strip(), [i for i in ids if i]


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
