"""Optional out-of-app caregiver alerts via a Telegram bot. Off unless both env vars are set.

Never blocks the pipeline (runs in a thread) and never raises: the dashboard alert is the primary channel.
"""

import logging
import threading

import httpx

from .config import Settings
from .config import settings as default_settings

log = logging.getLogger("kawan.notify")


class Notifier:
    def __init__(self, cfg: Settings = default_settings):
        self.cfg = cfg
        self.sent: list[str] = []  # for tests / dashboard

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.telegram_token and self.cfg.telegram_chat_id)

    def send(self, text: str):
        self.sent.append(text)
        if self.enabled:
            threading.Thread(target=self._post, args=(text,), daemon=True).start()

    def _post(self, text: str):
        try:
            httpx.post(
                f"https://api.telegram.org/bot{self.cfg.telegram_token}/sendMessage",
                json={"chat_id": self.cfg.telegram_chat_id, "text": text},
                timeout=10,
            )
        except Exception as e:
            log.warning("Telegram alert failed: %s", e)
