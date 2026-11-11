"""Optional out-of-app caregiver alerts via a Telegram bot. Off unless both env vars are set.

Several caregivers can be alerted at once: put their chat IDs in TELEGRAM_CHAT_ID separated by
commas, e.g. TELEGRAM_CHAT_ID=111111111,222222222,-1003333333333 (a negative ID is a group chat).

Never blocks the pipeline (runs in a thread) and never raises: the dashboard alert is the primary channel.
Each caregiver is messaged separately, so one wrong or blocked chat ID can't stop the others.
"""

import logging
import threading

import httpx

from .config import Settings
from .config import settings as default_settings

log = logging.getLogger("kawan.notify")


def parse_chat_ids(raw: str) -> list[str]:
    """Turn '111, 222,,333' into ['111', '222', '333'] (spaces and empty entries ignored, duplicates removed)."""
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part and part not in ids:
            ids.append(part)
    return ids


class Notifier:
    def __init__(self, cfg: Settings = default_settings):
        self.cfg = cfg
        self.chat_ids = parse_chat_ids(cfg.telegram_chat_id)
        self.sent: list[str] = []  # for tests / dashboard

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.telegram_token and self.chat_ids)

    def send(self, text: str):
        self.sent.append(text)
        if self.enabled:
            threading.Thread(target=self._post_all, args=(text,), daemon=True).start()

    def _post_all(self, text: str) -> int:
        """Message every caregiver. Returns how many messages Telegram accepted."""
        delivered = 0
        for chat_id in self.chat_ids:
            try:
                r = httpx.post(
                    f"https://api.telegram.org/bot{self.cfg.telegram_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                    timeout=10,
                )
                if r.status_code == 200:
                    delivered += 1
                else:
                    log.warning("Telegram alert to %s rejected: HTTP %s", chat_id, r.status_code)
            except Exception as e:
                log.warning("Telegram alert to %s failed: %s", chat_id, e)
        return delivered
