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


# ---------- in-app setup, private caregiver links and two-way replies ----------
import time  # noqa: E402

import pytest  # noqa: E402

from app.data_types import Detection  # noqa: E402
from app.database import Database  # noqa: E402
from app.hub import Hub  # noqa: E402

TOKEN = "123456789:" + "A" * 35


class FakeAPI:
    """Stands in for httpx.post/get on every Telegram method; records (method, payload)."""

    def __init__(self, me_ok=True):
        self.calls, self.me_ok = [], me_ok

    def post(self, url, json=None, timeout=None):
        self.calls.append((url.rsplit("/", 1)[1], json))
        return httpx.Response(200, json={"ok": True, "result": {}})

    def get(self, url, params=None, timeout=None):
        return httpx.Response(200, json={"ok": self.me_ok, "result": {"username": "kawan_test_bot"}})

    def sent_to(self, chat_id):
        return [p["text"] for m, p in self.calls if m == "sendMessage" and p["chat_id"] == chat_id]


@pytest.fixture
def tg(monkeypatch):
    fake = FakeAPI()
    monkeypatch.setattr(telegram_alerts.httpx, "post", fake.post)
    monkeypatch.setattr(telegram_alerts.httpx, "get", fake.get)
    hub = Hub(Settings(telegram_token="", telegram_chat_id="", checkin_timeout_s=5), Database(":memory:"))
    assert hub.notifier.connect(TOKEN)["ok"]
    return hub, fake


def start(chat_id, text, first="Farid"):
    return {
        "update_id": 1,
        "message": {"text": text, "chat": {"id": chat_id, "type": "private", "first_name": first}},
    }


def tap(chat_id, data, first="Farid"):
    return {
        "update_id": 2,
        "callback_query": {
            "id": "q1",
            "data": data,
            "from": {"first_name": first},
            "message": {"message_id": 9, "chat": {"id": chat_id, "first_name": first}},
        },
    }


def test_connect_checks_token_shape_and_with_telegram(monkeypatch):
    fake = FakeAPI(me_ok=False)
    monkeypatch.setattr(telegram_alerts.httpx, "get", fake.get)
    monkeypatch.setattr(telegram_alerts.httpx, "post", fake.post)
    n = Notifier(Settings(telegram_token="", telegram_chat_id=""), Database(":memory:"))
    assert not n.connect("not-a-token")["ok"]
    assert not n.connect(TOKEN)["ok"]  # Telegram said no
    assert n.token_source is None
    fake.me_ok = True
    assert n.connect(TOKEN)["ok"] and n.token_source == "app" and n.bot_username == "kawan_test_bot"
    assert TOKEN not in str(n.info())  # the token never goes to the dashboard


def test_caregiver_joins_only_with_the_private_link(tg):
    hub, fake = tg
    n = hub.notifier
    link = n.info()["link"]
    code = link.split("start=")[1]
    assert link.startswith("https://t.me/kawan_test_bot?start=")

    n.handle_update(start(555, "/start"))  # a stranger who just found the bot
    n.handle_update(start(555, "/start wrongcode"))
    n.handle_update(start(555, "/status"))
    assert not n.enabled and "private" in fake.sent_to("555")[0]
    assert len(fake.sent_to("555")) == 2  # /status from a stranger gets no reply at all

    n.handle_update(start(111, f"/start {code}"))
    assert n.enabled and n.info()["chats"][0]["name"] == "Farid"
    assert "Linked" in fake.sent_to("111")[0]
    assert n.link_code() != code  # one link = one caregiver
    n.handle_update(start(222, f"/start {code}", first="Aisyah"))  # reused link
    assert n.chat_ids == ["111"]


def test_alert_has_button_and_tap_acknowledges_and_tells_the_person(tg, monkeypatch):
    hub, fake = tg
    n = hub.notifier
    n.handle_update(start(111, f"/start {n.link_code()}"))
    n.handle_update(start(222, f"/start {n.link_code()}", first="Aisyah"))
    monkeypatch.setattr(telegram_alerts.threading, "Thread", _Inline)

    hub._detect(Detection("possible_fall", time.time(), ["hip dropped fast"], "u", "camera"), time.time())
    with hub.lock:  # no reply to the check-in within the timeout
        hub._record(hub.engine.tick(time.time() + 10))
    alerts = [p for m, p in fake.calls if m == "sendMessage" and "reply_markup" in p]
    assert alerts, "escalation should be sent with a button"
    iid = hub.engine.active.id
    assert alerts[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"ack:{iid}"
    assert "hip dropped fast" in alerts[0]["text"] and "999" in alerts[0]["text"]

    n.handle_update(tap(111, f"ack:{iid}"))
    assert hub.engine.incidents[iid].status == "acknowledged"
    assert "Farid has seen the alert" in hub.chat[-1]["text"]  # the person at home is told
    assert any("Farid is handling" in t for t in fake.sent_to("222"))  # the other caregiver too
    assert not any("Farid is handling" in t for t in fake.sent_to("111"))
    n.handle_update(tap(111, f"ack:{iid}"))  # second tap: harmless
    assert sum(1 for e in hub.store.recent_events(50) if e["kind"] == "acknowledged") == 1


def test_stranger_cannot_press_the_button(tg):
    hub, fake = tg
    hub._detect(Detection("possible_fall", time.time(), ["r"], "u", "camera"), time.time())
    iid = hub.engine.active.id
    hub.notifier.handle_update(tap(999, f"ack:{iid}"))
    assert hub.engine.incidents[iid].status == "open"


def test_status_and_stop_commands(tg):
    hub, fake = tg
    n = hub.notifier
    hub.set_profile({"user_name": "Aminah"})
    n.handle_update(start(111, f"/start {n.link_code()}"))
    n.handle_update(start(111, "/status"))
    status = fake.sent_to("111")[-1]
    assert "Aminah" in status and "All clear" in status
    n.handle_update(start(111, "/stop"))
    assert not n.enabled and "Stopped" in fake.sent_to("111")[-1]


def test_reset_keeps_the_telegram_setup(tg):
    hub, fake = tg
    hub.notifier.handle_update(start(111, f"/start {hub.notifier.link_code()}"))
    hub.reset()
    assert hub.notifier.enabled and hub.notifier.token_source == "app"


def test_env_setup_still_wins_and_cannot_be_removed_in_app():
    n = Notifier(Settings(telegram_token=TOKEN, telegram_chat_id="111"), Database(":memory:"))
    assert n.token_source == "env" and n.chats[0]["env"]
    assert not n.remove_chat("111")


class _Inline:
    """threading.Thread stand-in that runs the target immediately (deterministic tests)."""

    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self.target, self.args, self.kwargs = target, args, kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)
