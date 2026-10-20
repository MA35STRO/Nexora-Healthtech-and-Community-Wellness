"""Tests for the safety-critical logic: detector, reply classifier, context engine."""
import pytest

from app.assistant import classify, detect_lang
from app.config import Settings
from app.detector import FallDetector
from app.engine import ContextEngine
from app.models import Detection, Observation

CFG = Settings(checkin_timeout_s=20)


def feed(det, frames):
    """frames: list of (t, person, angle, hip_y). Returns detections."""
    out = []
    for t, person, angle, hip in frames:
        d = det.update(Observation(t, person, angle, hip, source="demo"))
        if d:
            out.append(d)
    return out


def standing(t0, t1):
    return [(t0 + i / 10, True, 5, 0.45) for i in range(int((t1 - t0) * 10))]


def fall_then_lie(t0, lie_s):
    # 0.6s rapid descent with torso rotating to horizontal, then lying still
    desc = [(t0 + i / 10, True, 5 + i * 14, 0.45 + i * 0.07) for i in range(7)]
    lie = [(t0 + 0.7 + i / 10, True, 85, 0.88) for i in range(int(lie_s * 10))]
    return desc + lie


# ---------- detector ----------
def test_fall_then_lying_still_is_flagged():
    d = FallDetector(CFG)
    out = feed(d, standing(0, 3) + fall_then_lie(3, 3))
    assert len(out) == 1
    assert "dropped" in out[0].reasons[0]
    assert any("horizontal" in r for r in out[0].reasons)


def test_walking_and_standing_never_flagged():
    d = FallDetector(CFG)
    walk = [(i / 10, True, 8 + (i % 4), 0.45 + 0.01 * (i % 3)) for i in range(200)]
    assert feed(d, walk) == []


def test_slowly_lying_down_not_flagged():
    d = FallDetector(CFG)
    slow = [(3 + i / 10, True, 5 + i * 1.6, 0.45 + i * 0.008) for i in range(50)]  # 5s descent
    lie = [(8 + i / 10, True, 85, 0.85) for i in range(40)]
    assert feed(d, standing(0, 3) + slow + lie) == []


def test_sitting_down_quickly_not_flagged():
    d = FallDetector(CFG)
    sit = [(3 + i / 10, True, 10, 0.45 + i * 0.05) for i in range(5)] + \
          [(3.5 + i / 10, True, 12, 0.70) for i in range(40)]
    assert feed(d, standing(0, 3) + sit) == []


def test_quick_recovery_not_flagged():
    d = FallDetector(CFG)
    frames = standing(0, 3) + fall_then_lie(3, 1.0) + standing(4.8, 8)
    assert feed(d, frames) == []


def test_drop_then_out_of_view_flagged_with_reason():
    d = FallDetector(CFG)
    desc = [(3 + i / 10, True, 5 + i * 8, 0.45 + i * 0.08) for i in range(5)]
    gone = [(3.5 + i / 10, False, 0, 0) for i in range(30)]
    out = feed(d, standing(0, 3) + desc + gone)
    assert len(out) == 1
    assert any("left the camera view" in r for r in out[0].reasons)


# ---------- reply classifier ----------
@pytest.mark.parametrize("text,intent", [
    ("I'm okay", "ok"), ("im fine thanks", "ok"), ("Saya okay", "ok"), ("tak apa, saya baik", "ok"),
    ("help", "help"), ("Tolong!", "help"), ("I'm not okay", "help"), ("saya tak ok", "help"),
    ("I can't get up", "help"), ("kaki saya sakit", "help"), ("okay but my leg hurts", "help"),
    ("good morning", "unclear"), ("what?", "unclear"), ("", "unclear"),
])
def test_classify(text, intent):
    assert classify(text) == intent


def test_detect_lang():
    assert detect_lang("Saya okay") == "ms"
    assert detect_lang("I'm okay") == "en"


# ---------- context engine ----------
def det(t=100.0):
    return Detection("possible_fall", t, ["reason"], "uncertain", "demo")


def test_fall_starts_checkin():
    e = ContextEngine(CFG)
    ev = e.on_detection(det(), 100)
    assert e.state == "check_in"
    assert [x.kind for x in ev] == ["possible_fall", "checkin_sent"]
    assert e.active.severity == "medium"


def test_user_ok_lowers_severity_without_escalation():
    e = ContextEngine(CFG)
    e.on_detection(det(), 100)
    reply, _ = e.on_user_message("I'm okay", 105)
    assert e.state == "attention"
    assert e.active.severity == "low" and not e.active.escalated
    assert e.tick(200) == []   # timeout no longer applies
    assert "caregiver" in reply.lower()


def test_no_response_escalates_after_timeout():
    e = ContextEngine(CFG)
    e.on_detection(det(), 100)
    assert e.tick(119) == []
    ev = e.tick(120)
    assert e.state == "escalated"
    assert e.active.user_response == "no_response" and e.active.severity == "critical"
    assert ev[0].kind == "escalated"


def test_help_escalates_immediately_malay():
    e = ContextEngine(CFG)
    e.on_detection(det(), 100)
    reply, _ = e.on_user_message("Tolong, saya tak boleh bangun", 103)
    assert e.state == "escalated" and e.active.user_response == "help"
    assert "penjaga" in reply   # replied in Malay


def test_unclear_reply_keeps_timer_running():
    e = ContextEngine(CFG)
    e.on_detection(det(), 100)
    e.on_user_message("good morning", 105)
    assert e.state == "check_in"
    e.tick(121)
    assert e.state == "escalated"


def test_help_without_incident_creates_critical_alert():
    e = ContextEngine(CFG)
    e.on_user_message("help me please", 50)
    assert e.state == "escalated" and e.active.kind == "help_request"


def test_duplicate_detection_merges():
    e = ContextEngine(CFG)
    e.on_detection(det(), 100)
    e.on_detection(det(), 104)
    assert len(e.incidents) == 1


def test_acknowledge_then_resolve_returns_to_monitoring():
    e = ContextEngine(CFG)
    e.on_detection(det(), 100)
    e.tick(130)
    iid = e.active.id
    e.acknowledge(iid, 131)
    assert e.incidents[iid].status == "acknowledged" and e.state == "escalated"
    e.resolve(iid, 140, "Visited, user is fine")
    assert e.state == "monitoring" and e.pending_prompt is None


def test_guessed_landmarks_never_trigger():
    """Upper-body-only view: MediaPipe's guessed hips may jump around — must be ignored."""
    d = FallDetector(CFG)
    frames = [Observation(i / 10, True, 5 if i < 30 else 85, 0.45 if i < 30 else 0.9,
                          "upper body only", "demo", full_body=False) for i in range(80)]
    assert [x for f in frames if (x := d.update(f))] == []
