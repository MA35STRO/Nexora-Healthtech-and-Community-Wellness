"""End-to-end over HTTP/WebSocket: browser pose stream, demo scenarios, medicines, vitals, daily check-in."""

import time

import pytest
from fastapi.testclient import TestClient
from test_demo_scenarios import wait_for
from test_health_features import pose

import app.main as main
from app.config import Settings
from app.database import Database
from app.hub import Hub


def make(**kw):
    cfg = Settings(
        **{"checkin_timeout_s": 3, "seed_history": False, "vitals_sim": False, "anthropic_api_key": "", **kw}
    )
    return Hub(cfg, Database(":memory:"))


@pytest.fixture
def client(monkeypatch):
    hub = make()
    monkeypatch.setattr(main, "hub", hub)
    with TestClient(main.app) as c:
        yield c, hub


def lerp(a, b, k):
    return [[pa[0] + (pb[0] - pa[0]) * k, pa[1] + (pb[1] - pa[1]) * k, pb[2]] for pa, pb in zip(a, b)]


def test_browser_landmarks_detect_a_real_fall(client):
    """Simulates what the browser sends: standing, a 0.5 s fall, then lying still."""
    c, hub = client
    up, down = pose(True), pose(False)
    with c.websocket_connect("/ws/perception") as ws:

        def send(lm, motion=0.01):
            ws.send_json({"lm": lm, "motion": motion})
            return ws.receive_json()

        for _ in range(15):
            assert send(up)["posture"] == "standing"
            time.sleep(0.05)
        for i in range(6):
            send(lerp(up, down, (i + 1) / 6), 0.05)
            time.sleep(0.08)
        end = time.time() + 4
        while time.time() < end and hub.engine.state == "monitoring":
            send(down, 0.0)
            time.sleep(0.1)
    assert hub.engine.state == "check_in"
    assert hub.engine.active.kind == "possible_fall" and hub.engine.active.source == "camera"
    assert any(m["kind"] == "checkin" for m in hub.chat)


def test_perception_ignores_garbage(client):
    c, hub = client
    with c.websocket_connect("/ws/perception") as ws:
        ws.send_json({"lm": None, "motion": "x"})
        assert ws.receive_json()["person"] is False
        ws.send_json({"lm": [[0, 0, 0]] * 500})
        ws.send_json({"lm": None})
        assert ws.receive_json()["person"] is False


def test_demo_inactivity_checks_in_then_escalates(client):
    c, hub = client
    assert c.post("/api/demo/inactivity").status_code == 200
    assert wait_for(lambda: hub.engine.state == "check_in", timeout=20)
    assert hub.engine.active.kind == "inactivity"
    assert wait_for(lambda: hub.engine.state == "escalated", timeout=6)
    c.post("/api/demo/stop")
    assert hub.inactivity.override_s is None


def test_demo_red_flag(client):
    c, hub = client
    c.post("/api/demo/red_flag")
    assert wait_for(lambda: hub.engine.state == "escalated", timeout=10)
    assert hub.engine.active.kind == "red_flag_symptom"


def test_demo_med_taken_and_missed(monkeypatch):
    hub = make()
    monkeypatch.setattr(main, "hub", hub)
    with TestClient(main.app) as c:
        c.post("/api/demo/med_taken")
        assert wait_for(lambda: any(e["kind"] == "med_taken" for e in hub.store.recent_events()), timeout=12)
        assert any(m["kind"] == "reminder" for m in hub.chat)
        c.post("/api/demo/med_missed")
        assert wait_for(
            lambda: any(i.kind == "missed_medication" for i in hub.engine.incidents.values()), timeout=20
        )
        assert hub.engine.state == "attention"  # a notice, not an emergency


def test_demo_low_spo2_with_fast_simulator(monkeypatch):
    hub = make(vitals_sim=True, vitals_interval_s=0.3, vitals_sustain_s=3)
    monkeypatch.setattr(main, "hub", hub)
    with TestClient(main.app) as c:
        c.post("/api/demo/low_spo2")
        assert wait_for(lambda: hub.engine.state == "check_in", timeout=15)
        assert hub.engine.active.kind == "vitals_alert"
        c.post("/api/demo/stop")
        assert hub.sim.mode == "normal"


def test_meds_crud_and_take(client):
    c, hub = client
    r = c.post("/api/meds", json={"name": "Aspirin", "dose": "100 mg", "times": ["10:00"]})
    mid = r.json()["id"]
    assert any(m["name"] == "Aspirin" for m in c.get("/api/meds").json()["schedule"])
    assert c.post("/api/meds", json={"name": "X", "times": ["25:99"]}).status_code == 400
    assert c.delete(f"/api/meds/{mid}").status_code == 200
    assert c.delete("/api/meds/nope").status_code == 404
    hub.meds.demo_dose(time.time(), 60)
    assert "taken" in c.post("/api/meds/take", json={}).json()["reply"]


def test_vitals_device_post_and_validation(client):
    c, hub = client
    assert c.post("/api/vitals", json={"spo2": 120}).status_code == 422
    assert c.post("/api/vitals", json={}).status_code == 400
    r = c.post("/api/vitals", json={"sys": 192, "dia": 124, "source": "omron"}).json()
    assert r["alert"] and hub.engine.active.kind == "vitals_alert"
    assert c.get("/api/state").json()["vitals"]["latest"]["source"] == "omron"


def test_wellness_api_and_insights(client):
    c, _ = client
    opts = c.get("/api/wellness/options").json()
    assert any(s["id"] == "chest_pain" for s in opts["symptoms"]) and opts["hotlines"]["emergency"] == "999"
    r = c.post("/api/wellness", json={"mood": 4, "pain": 1, "sleep_h": 7, "symptoms": []}).json()
    assert r["level"] == "self_care"
    ins = c.get("/api/insights").json()
    assert len(ins["activity"]) == 7 and ins["wellness"][-1]["level"] == "self_care"
    assert "percent" in ins["adherence"]


def test_chat_offline_answer_and_pillcheck(client):
    c, _ = client
    r = c.post("/api/chat", json={"text": "What is amlodipine?"}).json()
    assert r["route"] == "ask" and r["source"] == "offline" and "blood pressure" in r["reply"]
    assert c.post("/api/pillcheck", json={"image": "not base64!!"}).status_code == 400
    r = c.post("/api/pillcheck", json={"image": "data:image/jpeg;base64,aGk="}).json()
    assert r["source"] == "offline"


def test_seeded_history_is_labelled_simulated():
    hub = Hub(Settings(seed_history=True, vitals_sim=False, anthropic_api_key=""), Database(":memory:"))
    ins = hub.insights()
    assert ins["adherence"]["taken"] > 0
    assert all(r["simulated"] for r in ins["wellness"])
    assert any(d["simulated"] for d in ins["activity"])
