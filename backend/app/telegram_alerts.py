"""Caregiver alerts and replies through a Telegram bot. Optional: Kawan works fully without it.

Setting it up (no file editing needed):
  1. Create a bot with @BotFather and paste its token on the Caregiver page → Kawan tests it with getMe.
  2. Each caregiver opens the private link shown there (t.me/<bot>?start=<code>) and taps Start.
     Only someone holding that link can join, so a stranger who finds the bot gets nothing.
  3. Alerts arrive with an "I'm on it" button; /status and /stop work from the chat.

The older .env setup still works: TELEGRAM_BOT_TOKEN plus TELEGRAM_CHAT_ID (comma-separated for several
caregivers, a negative ID is a group chat). Real env vars win over what is saved in the app.

Kawan long-polls Telegram (getUpdates), so it needs no public URL, tunnel or webhook. Sending never blocks
the safety pipeline (it runs in a thread) and never raises: the dashboard alert is the primary channel, and
each caregiver is messaged separately so one wrong or blocked chat can't stop the others.
"""

import json
import logging
import re
import secrets
import threading
from typing import Callable, Optional

import httpx

from .config import Settings
from .config import settings as default_settings

log = logging.getLogger("kawan.notify")

API = "https://api.telegram.org"
TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
ACK_BUTTON = "✅ I'm on it"
HELP_TEXT = "Commands:\n/status — how they are right now\n/stop — stop receiving Kawan alerts in this chat"


def parse_chat_ids(raw: str) -> list[str]:
    """Turn '111, 222,,333' into ['111', '222', '333'] (spaces and empty entries ignored, duplicates removed)."""
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part and part not in ids:
            ids.append(part)
    return ids


def _chat_name(chat: dict, sender: Optional[dict] = None) -> str:
    if chat.get("title"):
        return str(chat["title"])[:60]
    who = sender or chat
    name = " ".join(x for x in (who.get("first_name"), who.get("last_name")) if x)
    return (name or who.get("username") or "Caregiver")[:60]


class Notifier:
    """Sends alerts to every linked caregiver and answers their taps and commands."""

    def __init__(self, cfg: Settings = default_settings, store=None):
        self.cfg = cfg
        self.store = store  # Database for the in-app setup; None = .env only (tests, scripts)
        self.sent: list[str] = []  # for tests / dashboard
        self.bot_username: Optional[str] = None
        # Set by the Hub. on_ack(incident_id, caregiver_name) -> reply text; status() -> summary text
        self.on_ack: Optional[Callable[[int, str], tuple[bool, str]]] = None
        self.status: Optional[Callable[[], str]] = None
        self.on_change: Optional[Callable[[], None]] = None
        self._stop: Optional[threading.Event] = None
        self.polling = False
        self.poll_error: Optional[str] = None

    # ---------- configuration ----------
    def _saved(self) -> dict:
        return (self.store.kv_get("telegram") if self.store else None) or {}

    def _save(self, data: dict):
        if self.store:
            self.store.kv_set("telegram", data)
        if self.on_change:
            self.on_change()

    @property
    def token(self) -> str:
        return self.cfg.telegram_token or self._saved().get("token", "")

    @property
    def token_source(self) -> Optional[str]:
        if self.cfg.telegram_token:
            return "env"
        return "app" if self._saved().get("token") else None

    @property
    def chats(self) -> list[dict]:
        """Everyone who gets alerts: chat IDs from .env first, then caregivers linked in the app."""
        out = [
            {"id": c, "name": f"Chat {c} (.env)", "env": True}
            for c in parse_chat_ids(self.cfg.telegram_chat_id)
        ]
        seen = {c["id"] for c in out}
        for c in self._saved().get("chats", []):
            if c["id"] not in seen:
                out.append({"id": c["id"], "name": c["name"], "env": False})
                seen.add(c["id"])
        return out

    @property
    def chat_ids(self) -> list[str]:
        return [c["id"] for c in self.chats]

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_ids)

    def link_code(self) -> str:
        saved = self._saved()
        if not saved.get("link_code"):
            saved["link_code"] = secrets.token_hex(5)
            self._save(saved)
        return saved["link_code"]

    def link_url(self) -> Optional[str]:
        bot = self.bot_username or self._saved().get("bot")
        return f"https://t.me/{bot}?start={self.link_code()}" if (bot and self.token) else None

    def info(self) -> dict:
        """What the dashboard may see. Never includes the token."""
        bot = self.bot_username or self._saved().get("bot")
        return {
            "telegram": self.enabled,
            "telegram_recipients": len(self.chat_ids) if self.enabled else 0,
            "bot": bot,
            "token_source": self.token_source,
            "link": self.link_url(),
            "chats": [{"id": c["id"], "name": c["name"], "env": c["env"]} for c in self.chats],
            "listening": self.polling,
            "error": self.poll_error,
        }

    # ---------- connect / disconnect (from the Caregiver page) ----------
    def connect(self, token: str) -> dict:
        token = token.strip()
        if not TOKEN_RE.match(token):
            return {
                "ok": False,
                "message": "That doesn't look like a bot token. It looks like 123456789:AA… and comes from @BotFather.",
            }
        try:
            r = httpx.get(f"{API}/bot{token}/getMe", timeout=10)
            data = r.json()
        except Exception as e:
            return {
                "ok": False,
                "message": f"Could not reach Telegram ({type(e).__name__}). Check the internet connection.",
            }
        if not data.get("ok"):
            return {"ok": False, "message": "Telegram rejected that token. Copy it again from @BotFather."}
        bot = data["result"].get("username", "")
        try:  # a webhook left over from elsewhere would block getUpdates
            httpx.post(f"{API}/bot{token}/deleteWebhook", json={}, timeout=10)
        except Exception:
            pass
        old = self._saved()
        same_bot = old.get("token") == token
        self.bot_username = bot
        self._save(
            {
                "token": token,
                "bot": bot,
                "chats": old.get("chats", []) if same_bot else [],
                "link_code": secrets.token_hex(5),
            }
        )
        self.poll_error = None
        return {
            "ok": True,
            "message": f"Connected to @{bot}. Now open the caregiver link below on each phone.",
            "bot": bot,
        }

    def disconnect(self) -> dict:
        self.bot_username = None
        self._save({})
        return {"ok": True}

    def remove_chat(self, chat_id: str) -> bool:
        saved = self._saved()
        chats = saved.get("chats", [])
        keep = [c for c in chats if c["id"] != str(chat_id)]
        if len(keep) == len(chats):
            return False
        saved["chats"] = keep
        self._save(saved)
        return True

    # ---------- sending ----------
    def send(self, text: str, incident_id: Optional[int] = None, ack_button: bool = False):
        self.sent.append(text)
        if self.enabled:
            markup = (
                {"inline_keyboard": [[{"text": ACK_BUTTON, "callback_data": f"ack:{incident_id}"}]]}
                if ack_button and incident_id is not None
                else None
            )
            threading.Thread(target=self._post_all, args=(text, markup), daemon=True).start()

    def send_test(self) -> dict:
        if not self.enabled:
            return {
                "ok": False,
                "delivered": 0,
                "message": "Connect a bot and link at least one caregiver first.",
            }
        n = self._post_all("👋 Test from Kawan: alerts to this chat are working.")
        total = len(self.chat_ids)
        return {
            "ok": n == total,
            "delivered": n,
            "message": f"Delivered to {n} of {total} caregiver chat{'s' if total != 1 else ''}.",
        }

    def _post_all(self, text: str, markup: Optional[dict] = None, skip: Optional[str] = None) -> int:
        """Message every caregiver. Returns how many messages Telegram accepted."""
        delivered = 0
        token = self.token
        for chat_id in self.chat_ids:
            if chat_id == skip:
                continue
            payload: dict = {"chat_id": chat_id, "text": text}
            if markup:
                payload["reply_markup"] = markup
            try:
                r = httpx.post(f"{API}/bot{token}/sendMessage", json=payload, timeout=10)
                if r.status_code == 200:
                    delivered += 1
                else:
                    log.warning("Telegram alert to %s rejected: HTTP %s", chat_id, r.status_code)
            except Exception as e:
                log.warning("Telegram alert to %s failed: %s", chat_id, e)
        return delivered

    def _call(self, method: str, payload: dict):
        try:
            httpx.post(f"{API}/bot{self.token}/{method}", json=payload, timeout=10)
        except Exception as e:
            log.warning("Telegram %s failed: %s", method, e)

    def _reply(self, chat_id, text: str):
        self._call("sendMessage", {"chat_id": chat_id, "text": text})

    # ---------- receiving (caregiver taps and commands) ----------
    def handle_update(self, u: dict):
        if "callback_query" in u:
            self._on_button(u["callback_query"])
            return
        msg = u.get("message") or {}
        text, chat = (msg.get("text") or "").strip(), msg.get("chat") or {}
        if not text or "id" not in chat:
            return
        chat_id = str(chat["id"])
        parts = text.split()
        cmd = parts[0].split("@")[0].lower() if parts[0].startswith("/") else ""
        arg = parts[1] if len(parts) > 1 else ""
        linked = chat_id in self.chat_ids

        if cmd == "/start":
            if linked:
                self._reply(chat_id, "This chat already gets Kawan alerts.\n\n" + HELP_TEXT)
            elif arg and secrets.compare_digest(arg, self.link_code()):
                saved = self._saved()
                name = _chat_name(chat, msg.get("from"))
                saved.setdefault("chats", []).append({"id": chat_id, "name": name})
                saved["link_code"] = secrets.token_hex(5)  # one link = one caregiver
                self._save(saved)
                self._reply(
                    chat_id,
                    f'✅ Linked. {name}, you\'ll get Kawan alerts here, each with an "{ACK_BUTTON}" button.\n\n'
                    + HELP_TEXT,
                )
            else:
                self._reply(
                    chat_id,
                    "This is a private Kawan bot. Ask the person who set up Kawan for the caregiver link "
                    "on their Caregiver page.",
                )
            return
        if not linked:
            return  # strangers get nothing about the person at home
        if cmd == "/status":
            self._reply(chat_id, self.status() if self.status else "Kawan is running.")
        elif cmd == "/stop":
            if self.remove_chat(chat_id):
                self._reply(chat_id, "Stopped. This chat won't get Kawan alerts any more.")
            else:
                self._reply(chat_id, "This chat is set in Kawan's .env file; remove it there to stop alerts.")
        else:
            self._reply(chat_id, HELP_TEXT)

    def _on_button(self, q: dict):
        msg = q.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id", ""))
        data = q.get("data") or ""
        answer = {"callback_query_id": q.get("id")}
        if chat_id not in self.chat_ids or not data.startswith("ack:") or not data[4:].isdigit():
            self._call("answerCallbackQuery", {**answer, "text": "This chat isn't linked to Kawan."})
            return
        name = _chat_name(msg.get("chat") or {}, q.get("from"))
        ok, text = self.on_ack(int(data[4:]), name) if self.on_ack else (False, "Kawan isn't ready.")
        self._call("answerCallbackQuery", {**answer, "text": text})
        if "message_id" in msg:  # swap the button for who took it, so nobody taps twice
            self._call(
                "editMessageReplyMarkup",
                {
                    "chat_id": chat_id,
                    "message_id": msg["message_id"],
                    "reply_markup": {
                        "inline_keyboard": [[{"text": f"👍 {name} is on it", "callback_data": "noop"}]]
                    },
                },
            )
        if ok:
            threading.Thread(
                target=self._post_all,
                kwargs={"text": f"👍 {name} is handling alert #{data[4:]}.", "skip": chat_id},
                daemon=True,
            ).start()

    # ---------- background listener ----------
    def start(self):
        if self._stop is None:
            self._stop = threading.Event()
            threading.Thread(target=self._poll_loop, args=(self._stop,), daemon=True).start()

    def stop(self):
        if self._stop:
            self._stop.set()
            self._stop = None

    def _poll_loop(self, stop: threading.Event):
        offset: Optional[int] = None
        polled_token = None
        while not stop.is_set():
            token = self.token
            if not token:
                self.polling = False
                stop.wait(3)
                continue
            if token != polled_token:  # new bot: learn its name, start from fresh updates
                polled_token, offset = token, None
                try:
                    me = httpx.get(f"{API}/bot{token}/getMe", timeout=10).json()
                    if me.get("ok"):
                        self.bot_username = me["result"].get("username")
                except Exception:
                    pass
            try:
                r = httpx.get(
                    f"{API}/bot{token}/getUpdates",
                    params={
                        "timeout": 25,
                        "offset": offset,
                        "allowed_updates": json.dumps(["message", "callback_query"]),
                    },
                    timeout=35,
                )
                data = r.json()
            except Exception as e:
                self._set_listening(False, f"Can't reach Telegram ({type(e).__name__}). Retrying…")
                stop.wait(5)
                continue
            if not data.get("ok"):
                self._set_listening(
                    False,
                    "Another program is reading this bot's messages (only one Kawan hub can use a bot)."
                    if r.status_code == 409
                    else f"Telegram said: {data.get('description', r.status_code)}",
                )
                stop.wait(10)
                continue
            self._set_listening(True, None)
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                if self.token != token:
                    break
                try:
                    self.handle_update(u)
                except Exception:
                    log.exception("Telegram update failed")
        self.polling = False

    def _set_listening(self, on: bool, error: Optional[str]):
        if (self.polling, self.poll_error) != (on, error):
            self.polling, self.poll_error = on, error
            if self.on_change:
                self.on_change()
