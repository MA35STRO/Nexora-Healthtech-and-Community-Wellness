"""Unit tests for the new modules: meds, routine, vitals, wellness, chat routing, LLM fallback, knowledge."""
import datetime as dt
from types import SimpleNamespace

import pytest

from app import assistant, knowledge, wellness
from app.config import Settings
from app.engine import ContextEngine
from app.hub import Hub
from app.llm import Brain, _alternate
from app.meds import MedScheduler, _at, adherence
from app.models import Detection, Observation
from app.perception import motion_score, observation_from_points
from app.routine import RoutineMonitor
from app.store import Store
from app.vitals import VitalsMonitor, VitalsSimulator

CFG = Settings(med_grace_s=3600, med_remind_again_s=600, inactivity_min_s=600, seed_history=False,
               vitals_sim=False, anthropic_api_key="")
DAY = dt.date(2026, 10, 20)


def T(hhmm, day=DAY):
    return _at(day, hhmm)


def sched(meds, start="07:00"):
    store = Store(":memory:")
    store.kv_set("meds", [{"id": f"m{i}", "name": n, "dose": "1 tab", "times": times, "instructions": "",
                           "purpose": "", "color": "#000"} for i, (n, times) in enumerate(meds)])
    return MedScheduler(store, CFG, now=T(start)), store


# ---------- medication ----------
def test_dose_becomes_due_then_reminds_again_then_missed():
    m, store = sched([("Metformin", ["08:00"])])
    assert m.tick(T("07:59")) == []
    acts = m.tick(T("08:00"))
    assert [a[0] for a in acts] == ["remind"]
    assert m.tick(T("08:05")) == []                       # not nagging every tick
    assert [a[0] for a in m.tick(T("08:10"))] == ["remind"]   # repeat after 10 min
    assert [a[0] for a in m.tick(T("09:00"))] == ["missed"]
    assert store.records("dose")[0]["status"] == "missed"


def test_take_marks_due_dose_and_stops_reminders():
    m, store = sched([("Metformin", ["08:00"])])
    m.tick(T("08:00"))
    dose, med = m.take(T("08:03"))
    assert med.name == "Metformin" and dose.status == "taken"
    assert m.tick(T("10:00")) == []
    assert adherence(store, T("12:00"))["percent"] == 100


def test_take_early_within_an_hour_counts_but_not_earlier():
    m, _ = sched([("Amlodipine", ["09:00"])])
    assert m.take(T("07:30")) is None
    assert m.take(T("08:15"))[0].status == "taken"


def test_doses_before_start_are_never_invented():
    m, _ = sched([("Metformin", ["08:00", "20:00"])], start="12:00")
    acts = m.tick(T("12:01"))
    assert acts == []   # 08:00 dose wasn't tracked, so it isn't "missed"
    assert [d["due_t"] for d in m.today(T("12:01"))] == [T("20:00")]


def test_snooze_delays_reminder():
    cfg = Settings(med_snooze_s=600, med_grace_s=3600, seed_history=False)
    m, _ = sched([("Metformin", ["08:00"])])
    m.cfg = cfg
    m.tick(T("08:00"))
    assert m.snooze(T("08:01"))
    assert m.tick(T("08:05")) == []
    assert [a[0] for a in m.tick(T("08:11"))] == ["remind"]


def test_restart_does_not_rerun_finished_doses():
    m, store = sched([("Metformin", ["08:00"])])
    m.tick(T("08:00"))
    m.take(T("08:02"))
    m2 = MedScheduler(store, CFG, now=T("08:30"))
    assert m2.tick(T("10:00")) == []


# ---------- routine / inactivity ----------
def still(t0, secs, motion=0.0, person=True, posture="sitting"):
    return [Observation(t0 + i, person, 10, 0.6, posture, "camera", True, motion) for i in range(secs)]


def run(r, obs):
    return [d for o in obs if (d := r.update(o))]


def test_inactivity_flagged_once_after_threshold_in_waking_hours():
    r = RoutineMonitor(Store(":memory:"), CFG)
    out = run(r, still(T("10:00"), 700))
    assert len(out) == 1 and out[0].kind == "inactivity"
    assert "No movement" in out[0].reasons[0]


def test_inactivity_not_flagged_at_night_or_when_moving_or_out_of_view():
    r = RoutineMonitor(Store(":memory:"), CFG)
    assert run(r, still(T("02:00"), 900)) == []
    r = RoutineMonitor(Store(":memory:"), CFG)
    assert run(r, still(T("10:00"), 900, motion=0.05)) == []
    r = RoutineMonitor(Store(":memory:"), CFG)
    assert run(r, still(T("10:00"), 900, person=False)) == []


def test_learned_baseline_raises_threshold():
    r = RoutineMonitor(Store(":memory:"), CFG)
    r.baseline["10"] = [1200] * 10   # this person usually reads quietly for 20 min at 10am
    assert r.threshold(T("10:30")) == pytest.approx(1800)
    assert run(r, still(T("10:00"), 1000)) == []


def test_movement_resets_stillness_and_is_learned():
    r = RoutineMonitor(Store(":memory:"), CFG)
    run(r, still(T("10:00"), 300) + still(T("10:00") + 300, 2, motion=0.05))
    assert r.still_since is None and r.baseline["10"] == [300]


# ---------- vitals ----------
def feed_vitals(mon, values, t0=0, step=2, **base):
    out = []
    for i, v in enumerate(values):
        reading = {"hr": 75, "spo2": 97, "sys": 125, "dia": 80, "temp": 36.7, **base, **v}
        if d := mon.add(reading, t0 + i * step, "simulated"):
            out.append(d)
    return out


def test_single_low_spo2_reading_is_ignored_but_sustained_alerts():
    mon = VitalsMonitor(Settings(vitals_sustain_s=20))
    assert feed_vitals(mon, [{"spo2": 85}] + [{}] * 12) == []
    mon = VitalsMonitor(Settings(vitals_sustain_s=20))
    out = feed_vitals(mon, [{"spo2": 89}] * 12)
    assert len(out) == 1 and "SpO2" in out[0].reasons[0] and "SIMULATED" in out[0].uncertainty


def test_bp_crisis_single_reading_and_cooldown():
    mon = VitalsMonitor(Settings())
    out = feed_vitals(mon, [{"sys": 190, "dia": 100}] * 5)
    assert len(out) == 1 and "crisis" in out[0].reasons[0]


def test_simulator_modes_drift_toward_targets():
    s = VitalsSimulator(seed=1)
    normal = [s.next() for _ in range(20)]
    assert all(r["spo2"] >= 94 for r in normal)
    s.mode = "hypoxia"
    low = [s.next() for _ in range(20)][-5:]
    assert all(r["spo2"] < 92 for r in low)


# ---------- wellness / red flags ----------
@pytest.mark.parametrize("text,expect", [
    ("I have chest pain", "Chest pain or pressure"), ("saya sakit dada", "Chest pain or pressure"),
    ("I can't breathe properly", "Difficulty breathing"), ("sesak nafas", "Difficulty breathing"),
    ("my face is drooping", "Face drooping (possible stroke sign)"), ("tangan kebas", "Arm or leg weakness on one side (possible stroke sign)"),
    ("I fainted this morning", "Fainting or collapse"), ("saya rasa nak bunuh diri", "Thoughts of self-harm"),
])
def test_red_flags_en_bm(text, expect):
    assert expect in wellness.red_flags(text)


def test_no_red_flags_in_ordinary_text():
    assert wellness.red_flags("I had nasi lemak and feel a bit tired") == []


def test_triage_levels():
    assert wellness.triage(4, 1, 7, [])["level"] == "self_care"
    assert wellness.triage(4, 5, 7, ["cough"])["level"] == "routine"
    assert wellness.triage(4, 9, 7, [])["level"] == "urgent"
    r = wellness.triage(4, 1, 7, ["chest_pain"])
    assert r["level"] == "emergency" and any("999" in a for a in r["advice"])
    assert any("HEAL" in a for a in wellness.triage(1, 0, 7, [])["advice"])


# ---------- chat routing ----------
@pytest.mark.parametrize("text,in_checkin,flag,expect", [
    ("I'm okay", True, False, "checkin_reply"),
    ("what is metformin?", True, False, "checkin_reply"),   # never bypass a pending check-in
    ("help me", False, False, "help"),
    ("can you help me understand my blood test?", False, False, "ask"),
    ("what causes chest pain?", False, True, "ask"),
    ("I have chest pain", False, True, "red_flag"),
    ("I took my medicine", False, False, "med_taken"),
    ("saya dah makan ubat", False, False, "med_taken"),
    ("when is my next medicine?", False, False, "med_schedule"),
    ("remind me later", False, False, "med_snooze"),
    ("daily check-in", False, False, "wellness"),
    ("my leg hurts", False, False, "help"),
    ("what is diabetes", False, False, "ask"),
    ("apa itu darah tinggi?", False, False, "ask"),
])
def test_route(text, in_checkin, flag, expect):
    assert assistant.route(text, in_checkin, flag) == expect


# ---------- engine: new kinds ----------
def test_red_flag_escalates_immediately():
    e = ContextEngine(CFG)
    e.report_red_flag(["Chest pain or pressure"], "I have chest pain", 10)
    assert e.state == "escalated" and e.active.severity == "critical"


def test_missed_med_is_notice_and_does_not_hide_fall_checkin():
    e = ContextEngine(CFG)
    e.on_detection(Detection("possible_fall", 10, ["r"], "u", "camera"), 10)
    e.on_detection(Detection("missed_medication", 11, ["r"], "u", "meds"), 11)
    assert e.state == "check_in" and e.active.kind == "possible_fall"
    assert e.pending_prompt and "fall" in e.pending_prompt


def test_ok_answers_all_pending_checkins():
    e = ContextEngine(CFG)
    e.on_detection(Detection("possible_fall", 10, ["r"], "u", "camera"), 10)
    e.on_detection(Detection("vitals_alert", 11, ["r"], "u", "vitals"), 11)
    e.on_user_message("I'm okay", 12)
    assert e.state == "attention" and e.tick(1000) == []


def test_each_pending_checkin_times_out():
    e = ContextEngine(CFG)
    e.on_detection(Detection("inactivity", 10, ["r"], "u", "camera"), 10)
    e.tick(10 + CFG.checkin_timeout_s)
    assert e.state == "escalated" and e.active.user_response == "no_response"


# ---------- LLM + knowledge ----------
def test_knowledge_finds_topics_en_bm():
    assert knowledge.answer("what is metformin for?")["id"] == "metformin"
    assert knowledge.answer("apa itu darah tinggi", "ms")["id"] == "hypertension"
    assert "BE-FAST" in knowledge.answer("signs of stroke")["text"]
    assert knowledge.answer("quantum chromodynamics") is None


def test_brain_offline_uses_knowledge_base():
    b = Brain(Settings(anthropic_api_key=""))
    assert not b.online
    reply, src = b.answer("what is hypoglycaemia", "en", "", [])
    assert src == "offline" and "4 mmol/L" in reply


class FakeClient:
    def __init__(self, fail=False, text="Metformin helps lower blood sugar."):
        self.fail, self.text, self.calls = fail, text, []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise TimeoutError("network down")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])


def test_brain_uses_claude_with_grounding_and_falls_back_on_error():
    fake = FakeClient()
    b = Brain(Settings(), client=fake)
    reply, src = b.answer("what is metformin", "en", "Medicines: Metformin", [{"from": "assistant", "text": "hi"}])
    assert src == "claude" and reply.startswith("Metformin")
    kw = fake.calls[0]
    assert "NOT a doctor" in kw["system"] and "Metformin" in kw["system"]
    assert kw["messages"][0]["role"] == "user"
    reply, src = Brain(Settings(), client=FakeClient(fail=True)).answer("what is metformin", "en", "", [])
    assert src == "offline" and "blood sugar" in reply


def test_pill_check_parses_json_and_rejects_unknown_match():
    fake = FakeClient(text='Sure: {"medicine": "Metformin", "strength": "500 mg", "matches": "Metformin", '
                           '"confidence": "high", "note": "This looks like your Metformin."}')
    r = Brain(Settings(), client=fake).read_medicine("aGk=", ["Metformin"], "en")
    assert r["matches"] == "Metformin" and r["source"] == "claude"
    fake.text = '{"medicine": "Panadol", "matches": "Panadol", "confidence": "high", "note": ""}'
    assert Brain(Settings(), client=fake).read_medicine("aGk=", ["Metformin"], "en")["matches"] is None
    assert Brain(Settings(anthropic_api_key="")).read_medicine("aGk=", [], "en")["source"] == "offline"


def test_alternate_merges_and_starts_with_user():
    msgs = _alternate([{"role": "assistant", "content": "a"}, {"role": "user", "content": "b"},
                       {"role": "user", "content": "c"}])
    assert msgs == [{"role": "user", "content": "b\nc"}]


def test_chat_question_never_reaches_llm_during_checkin():
    fake = FakeClient()
    hub = Hub(CFG, Store(":memory:"), brain=Brain(CFG, client=fake))
    hub._detect(Detection("possible_fall", 1, ["r"], "u", "camera"), 1)
    r = hub.user_message("what is metformin?")
    assert r["route"] == "checkin_reply" and fake.calls == []
    assert hub.engine.state == "check_in"


def test_hub_routes_med_taken_and_red_flag():
    hub = Hub(CFG, Store(":memory:"))
    hub.meds.demo_dose(__import__("time").time(), 60)
    assert "taken" in hub.user_message("I took my medicine")["reply"]
    r = hub.user_message("Saya sakit dada")
    assert r["route"] == "red_flag" and "999" in r["reply"] and hub.engine.state == "escalated"
    assert any("BAYMAX" in s for s in hub.notifier.sent)


def test_wellness_emergency_escalates_and_records():
    hub = Hub(CFG, Store(":memory:"))
    res = hub.submit_wellness({"mood": 3, "pain": 2, "sleep_h": 7, "symptoms": ["breathless"], "note": ""})
    assert res["level"] == "emergency" and hub.engine.state == "escalated"
    assert hub.store.records("wellness")[0]["level"] == "emergency"


# ---------- perception from browser landmarks ----------
def pose(standing=True):
    pts = [[0.5, 0.5, 0.0]] * 33
    pts = [list(p) for p in pts]
    if standing:
        for i, (x, y) in {11: (0.45, 0.3), 12: (0.55, 0.3), 23: (0.46, 0.55), 24: (0.54, 0.55),
                          25: (0.46, 0.75), 26: (0.54, 0.75)}.items():
            pts[i] = [x, y, 0.99]
    else:   # lying: shoulders and hips level
        for i, (x, y) in {11: (0.2, 0.85), 12: (0.2, 0.88), 23: (0.5, 0.86), 24: (0.5, 0.89),
                          25: (0.7, 0.86), 26: (0.7, 0.89)}.items():
            pts[i] = [x, y, 0.99]
    return pts


def test_observation_from_points():
    o = observation_from_points(pose(True), 1.0, 0.01)
    assert o.person and o.full_body and o.posture == "standing" and o.torso_angle < 10
    o = observation_from_points(pose(False), 1.0)
    assert o.posture == "lying" and o.torso_angle > 60
    assert not observation_from_points(None, 1.0).person


def test_motion_score():
    a = pose(True)
    b = [[x + 0.01, y, v] for x, y, v in a]
    assert motion_score(None, a) is None
    assert motion_score(a, b) == pytest.approx(0.01)
