"""Telegram caregiver alerts: one or many caregivers, and one bad chat ID never blocks the rest."""

import httpx

from app import telegram_alerts
from app.config import Settings
from app.telegram_alerts import Notifier, parse_chat_ids


def test_chat_id_list_parsing():
    assert parse_chat_ids("") == []
    assert parse_chat_ids("111") == ["111"]
    assert parse_chat_ids(" 111, 222 ,,333, 111 ") == ["111", "222", "333"]
    assert parse_chat_ids("-1003333333333") == ["-1003333333333"]  # group chat


def test_off_without_token_or_chat_ids():
    assert not Notifier(Settings(telegram_token="", telegram_chat_id="111")).enabled
    assert not Notifier(Settings(telegram_token="t", telegram_chat_id=" , ")).enabled
    assert Notifier(Settings(telegram_token="t", telegram_chat_id="111")).enabled


class FakeTelegram:
    """Stands in for httpx.post: records who was messaged; chat IDs in `bad` fail."""

    def __init__(self, bad=(), raises=()):
        self.calls, self.bad, self.raises = [], set(bad), set(raises)

    def __call__(self, url, json, timeout):
        self.calls.append(json["chat_id"])
        if json["chat_id"] in self.raises:
            raise httpx.ConnectError("no network")
        return httpx.Response(400 if json["chat_id"] in self.bad else 200)


def test_every_caregiver_gets_the_alert(monkeypatch):
    fake = FakeTelegram()
    monkeypatch.setattr(telegram_alerts.httpx, "post", fake)
    n = Notifier(Settings(telegram_token="t", telegram_chat_id="111,222,333"))
    assert n._post_all("🚨 Kawan: possible fall") == 3
    assert fake.calls == ["111", "222", "333"]


def test_one_bad_chat_id_does_not_block_the_others(monkeypatch):
    fake = FakeTelegram(bad={"222"}, raises={"333"})
    monkeypatch.setattr(telegram_alerts.httpx, "post", fake)
    n = Notifier(Settings(telegram_token="t", telegram_chat_id="111,222,333,444"))
    assert n._post_all("🚨 Kawan: possible fall") == 2  # 111 and 444 still delivered
    assert fake.calls == ["111", "222", "333", "444"]


def test_single_chat_id_still_works(monkeypatch):
    """Existing setups with one TELEGRAM_CHAT_ID keep working unchanged."""
    fake = FakeTelegram()
    monkeypatch.setattr(telegram_alerts.httpx, "post", fake)
    assert Notifier(Settings(telegram_token="t", telegram_chat_id="111"))._post_all("hi") == 1
    assert fake.calls == ["111"]
