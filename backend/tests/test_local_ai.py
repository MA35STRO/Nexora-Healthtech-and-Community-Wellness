"""Local AI through Ollama: same grounding and safety as Claude, no API key, nothing leaves the PC."""

import httpx
import pytest

from app import ai_answers
from app.ai_answers import AIAnswers, OllamaChat
from app.config import Settings
from app.database import Database
from app.hub import Hub


class FakeOllama:
    """Stands in for httpx.post/get against Ollama's /api/chat and /api/tags."""

    def __init__(
        self, reply="Metformin helps lower blood sugar.\nUSED: metformin", models=("gemma3:4b",), down=False
    ):
        self.reply, self.models, self.down, self.calls = reply, list(models), down, []

    def post(self, url, json=None, timeout=None):
        if self.down:
            raise httpx.ConnectError("refused")
        self.calls.append(json)
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": self.reply}},
            request=httpx.Request("POST", url),
        )

    def get(self, url, timeout=None):
        if self.down:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"models": [{"name": m} for m in self.models]})


@pytest.fixture
def ollama(monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(ai_answers.httpx, "post", fake.post)
    monkeypatch.setattr(ai_answers.httpx, "get", fake.get)
    return fake


def local(model="gemma3:4b"):
    return AIAnswers(Settings(), local=OllamaChat("http://127.0.0.1:11434", model, 30))


def test_answer_is_grounded_and_cited(ollama):
    r = local().answer("what is metformin", "en", "Medicines: none", [])
    assert r["source"] == "local" and r["reply"] == "Metformin helps lower blood sugar."
    assert r["refs"] and "metformin" in r["refs"][0]["title"].lower()
    sent = ollama.calls[0]
    assert sent["model"] == "gemma3:4b" and sent["stream"] is False
    assert sent["messages"][0]["role"] == "system" and "REFERENCE NOTES" in sent["messages"][0]["content"]
    assert sent["messages"][-1] == {"role": "user", "content": "what is metformin"}


def test_ollama_down_falls_back_to_the_offline_library(ollama):
    ollama.down = True
    r = local().answer("what is metformin", "en", "", [])
    assert r["source"] == "offline" and r["refs"]


def test_pill_check_sends_the_photo_to_the_local_model(ollama):
    ollama.reply = '{"text": "METFORMIN 500 mg", "medicine": "METFORMIN", "strength": "500 mg"}'
    r = local().read_medicine("aGk=", ["Metformin"], "en")
    assert r["matches"] == "Metformin" and r["source"] == "local"
    assert ollama.calls[0]["messages"][-1]["images"] == ["aGk="]


def test_check_explains_what_is_wrong(ollama):
    assert local().check()[0]
    assert "ollama pull" in local("llama3.2:3b").check()[1]  # not installed
    ollama.down = True
    assert "isn't running" in local().check()[1]


def test_hub_connects_disconnects_and_keeps_it_through_reset(ollama):
    hub = Hub(Settings(anthropic_api_key="", ollama_model=""), Database(":memory:"))
    assert not hub.ai.online and hub.local_models()["models"] == ["gemma3:4b"]
    r = hub.connect_local("")  # picks the installed gemma3 model
    assert r["ok"] and r["model"] == "gemma3:4b"
    snap = hub.snapshot()["ai"]
    assert snap["provider"] == "local" and snap["model"] == "gemma3:4b" and snap["local_source"] == "app"
    hub.reset()
    assert hub.ai.provider == "local"  # "reset data" keeps the AI connection
    hub.disconnect_local()
    assert not hub.ai.online


def test_local_model_wins_over_claude_and_falls_back_to_it():
    hub = Hub(Settings(anthropic_api_key="sk-ant-" + "x" * 40, ollama_model=""), Database(":memory:"))
    assert hub.ai.provider == "claude"
    hub.store.kv_set("ollama_model", "gemma3:4b")
    hub.ai = hub._ai_from_saved_key()
    assert hub.ai.provider == "local"
    hub.disconnect_local()
    assert hub.ai.provider == "claude"


def test_nothing_installed_gives_clear_instructions(ollama):
    ollama.models = []
    hub = Hub(Settings(anthropic_api_key="", ollama_model=""), Database(":memory:"))
    r = hub.connect_local("")
    assert not r["ok"] and "ollama pull" in r["message"]


# ---------- streaming: words appear as they are written ----------
from contextlib import contextmanager  # noqa: E402

from app.ai_answers import visible_part  # noqa: E402


def test_visible_part_never_shows_the_used_line():
    assert visible_part("Metformin lowers sugar.") == "Metformin lowers sugar."
    assert visible_part("Metformin lowers sugar.\nU") == "Metformin lowers sugar."
    assert visible_part("Metformin lowers sugar.\nUSE") == "Metformin lowers sugar."
    assert visible_part("Metformin lowers sugar.\nUSED: metf") == "Metformin lowers sugar."
    assert visible_part("Call us") == "Call us"  # a word, not the start of the USED line


def stream_fake(monkeypatch, pieces):
    lines = [f'{{"message": {{"content": {p!r}}}, "done": false}}'.replace("'", '"') for p in pieces]
    lines.append('{"done": true}')

    class R:
        def raise_for_status(self):
            pass

        def iter_lines(self):
            return iter(lines)

    @contextmanager
    def fake_stream(method, url, json=None, timeout=None):
        assert json["stream"] is True
        yield R()

    monkeypatch.setattr(ai_answers.httpx, "stream", fake_stream)


def test_streamed_answer_shows_progress_then_the_cited_reply(monkeypatch, ollama):
    stream_fake(monkeypatch, ["Metformin ", "helps lower ", "blood sugar.", "\nUSED: ", "metformin"])
    seen = []
    r = local().answer("what is metformin", "en", "", [], on_partial=seen.append)
    assert seen[0] == "Metformin" and seen[-1] == "Metformin helps lower blood sugar."
    assert not any("USED" in s for s in seen)
    assert r["reply"] == "Metformin helps lower blood sugar." and r["refs"] and r["source"] == "local"


def test_hub_draft_bubble_is_replaced_by_the_final_reply(monkeypatch, ollama):
    stream_fake(monkeypatch, ["Metformin helps.", "\nUSED: metformin"])
    hub = Hub(Settings(anthropic_api_key="", ollama_model=""), Database(":memory:"))
    hub.ai = local()
    drafts = []
    real_partial_answer = hub.ai.answer

    def spy(*a, on_partial=None, **k):
        def watch(text):
            on_partial(text)
            drafts.append([dict(m) for m in hub.chat if m.get("partial")])

        return real_partial_answer(*a, on_partial=watch, **k)

    hub.ai.answer = spy
    r = hub.user_message("what is metformin")
    assert r["source"] == "local" and r["reply"] == "Metformin helps."
    assert drafts and drafts[-1][0]["text"] == "Metformin helps."  # shown while being written
    assert not any(m.get("partial") for m in hub.chat)  # the draft is gone afterwards
    assert [m["text"] for m in hub.chat if m["from"] == "assistant"] == ["Metformin helps."]


def test_pill_check_tries_the_unmirrored_photo_when_the_first_read_fails(monkeypatch):
    reads = iter(
        [
            '{"text": "J38AJ YOARRRY", "medicine": null, "strength": null}',  # mirrored: unreadable
            '{"text": "METFORMIN 500 mg", "medicine": "METFORMIN", "strength": "500 mg"}',  # flipped: readable
        ]
    )
    ai = AIAnswers(Settings(), local=OllamaChat("http://x", "gemma3:4b", 5))
    sent = []
    monkeypatch.setattr(
        ai.local, "complete", lambda s, m, n, t, image_b64="": sent.append(image_b64) or next(reads)
    )
    r = ai.read_medicine("mirrored", ["Metformin"], "en", alternates=["flipped"])
    assert r["matches"] == "Metformin" and sent == ["mirrored", "flipped"]
    sent.clear()
    reads = iter(['{"text": "METFORMIN 500 mg", "medicine": "METFORMIN"}'])
    r = ai.read_medicine("good", ["Metformin"], "en", alternates=["flipped"])
    assert r["matches"] == "Metformin" and sent == ["good"]  # first read worked: no second call
