"""End-to-end: demo scenario → fall detector → safety engine → database → API. Runs in real time (~10s each)."""

import time

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.config import Settings
from app.database import Database
from app.hub import Hub


@pytest.fixture
def client(monkeypatch):
    hub = Hub(Settings(checkin_timeout_s=3), Database(":memory:"))
    monkeypatch.setattr(main, "hub", hub)
    with TestClient(main.app) as c:
        yield c, hub


def wait_for(fn, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.1)
    return False


def test_fall_no_response_escalates_and_caregiver_resolves(client):
    c, hub = client
    assert c.post("/api/demo/fall_no_response").status_code == 200
    assert wait_for(lambda: hub.engine.state == "check_in")
    assert wait_for(lambda: hub.engine.state == "escalated", timeout=6)  # 3s timeout in this test
    s = c.get("/api/state").json()
    inc = s["active_incident"]
    assert inc["user_response"] == "no_response" and inc["severity"] == "critical"
    assert inc["source"] == "demo"
    assert c.post(f"/api/incidents/{inc['id']}/ack").status_code == 200
    assert c.post(f"/api/incidents/{inc['id']}/resolve", json={"note": "checked"}).status_code == 200
    assert c.get("/api/state").json()["state"] == "monitoring"
    c.post("/api/demo/stop")


def test_fall_help_scenario_escalates_via_scripted_reply(client):
    c, hub = client
    c.post("/api/demo/fall_help")
    assert wait_for(lambda: hub.engine.state == "escalated")
    assert hub.engine.active.user_response == "help"
    kinds = [e["kind"] for e in c.get("/api/state").json()["events"]]
    assert {"possible_fall", "checkin_sent", "user_message", "escalated"} <= set(kinds)


def test_chat_ok_during_checkin(client):
    c, hub = client
    c.post("/api/demo/fall")
    assert wait_for(lambda: hub.engine.state == "check_in")
    r = c.post("/api/chat", json={"text": "Saya okay"}).json()
    assert "penjaga" in r["reply"]
    assert hub.engine.state == "attention"


def test_normal_scenario_raises_nothing(client):
    c, hub = client
    c.post("/api/demo/normal")
    time.sleep(1)
    assert wait_for(lambda: hub.demo_name is None, timeout=15)
    assert hub.engine.state == "monitoring" and not hub.engine.incidents


def test_websocket_pushes_snapshot(client):
    c, _ = client
    with c.websocket_connect("/ws") as ws:
        snap = ws.receive_json()
        assert snap["state"] == "monitoring" and "fall" in snap["demo"]["scenarios"]
