"""Demo scenarios: synthetic pose-feature streams that go through the REAL detector + engine.

Each scenario is a list of steps. A step is either a pose segment (posture, seconds, how angle
and hip move) or a scripted user reply. Nothing here decides alerts — the pipeline does.
Optional "setup" makes slow real-world things demo-sized (e.g. an 8 s inactivity threshold instead of
minutes, a dose due right now, a simulated oxygen drop) — all clearly labelled SIMULATED.
"""
from dataclasses import dataclass
from typing import Optional

FPS = 10


@dataclass
class Segment:
    seconds: float
    angle: tuple[float, float]   # torso angle start → end
    hip: tuple[float, float]     # hip_y start → end
    posture: str = "standing"
    person: bool = True
    say: Optional[str] = None    # scripted user reply sent at the start of this segment
    motion: Optional[float] = None   # landmark movement per frame; None = derive from angle/hip change


STAND = Segment(3, (6, 6), (0.45, 0.45))
WALK = Segment(6, (8, 8), (0.45, 0.47), "standing", motion=0.02)
IDLE = Segment(1, (8, 8), (0.45, 0.45), "standing", motion=0.02)
SIT = [Segment(1.2, (8, 12), (0.45, 0.68), "sitting"), Segment(5, (12, 12), (0.68, 0.68), "sitting")]
FALL = [Segment(0.6, (6, 82), (0.45, 0.88), "lying"), Segment(5, (84, 84), (0.88, 0.88), "lying")]

SCENARIOS: dict[str, dict] = {
    "normal": {"label": "Normal activity (walking)", "steps": [STAND, WALK, STAND]},
    "sitting": {"label": "Person sits down", "steps": [STAND, *SIT]},
    "fall": {"label": "Possible fall (no scripted reply)", "steps": [STAND, *FALL]},
    "fall_no_response": {"label": "Fall, then no response",
                         "steps": [STAND, *FALL, Segment(30, (84, 84), (0.88, 0.88), "lying")]},
    "fall_ok": {"label": "Fall, user says they're okay",
                "steps": [STAND, *FALL, Segment(2, (84, 84), (0.88, 0.88), "lying", say="I'm okay, just slipped"),
                          Segment(1.5, (60, 10), (0.88, 0.5), "sitting"), STAND]},
    "fall_help": {"label": "Fall, user asks for help (BM)",
                  "steps": [STAND, *FALL, Segment(4, (84, 84), (0.88, 0.88), "lying",
                                                  say="Tolong, saya tak boleh bangun")]},
    "inactivity": {"label": "Sits very still for too long (no reply)",
                   "steps": [STAND, *SIT, Segment(40, (12, 12), (0.68, 0.68), "sitting", motion=0.0)],
                   "setup": {"inactivity_s": 8}},
    "med_taken": {"label": "Medicine reminder → user takes it",
                  "steps": [IDLE, Segment(5, (8, 8), (0.45, 0.45), "standing", motion=0.02),
                            Segment(3, (8, 8), (0.45, 0.45), "standing", say="I took my medicine", motion=0.02)],
                  "setup": {"dose_grace_s": 60}},
    "med_missed": {"label": "Medicine reminder → dose missed",
                   "steps": [Segment(22, (8, 8), (0.45, 0.46), "standing", motion=0.02)],
                   "setup": {"dose_grace_s": 15}},
    "low_spo2": {"label": "Oxygen level drops (simulated vitals)",
                 "steps": [Segment(45, (10, 10), (0.66, 0.66), "sitting", motion=0.02)],
                 "setup": {"vitals": "hypoxia"}},
    "red_flag": {"label": "User reports chest pain (BM)",
                 "steps": [IDLE, Segment(4, (10, 10), (0.66, 0.66), "sitting", motion=0.02,
                                         say="Saya sakit dada dan sesak nafas")]},
}


def frames(steps: list[Segment]):
    """Yield (dt_offset, Segment, angle, hip, motion, scripted_reply) at FPS."""
    t = 0.0
    prev = None
    for seg in steps:
        n = max(1, int(seg.seconds * FPS))
        for i in range(n):
            k = i / max(1, n - 1)
            angle = seg.angle[0] + (seg.angle[1] - seg.angle[0]) * k
            hip = seg.hip[0] + (seg.hip[1] - seg.hip[0]) * k
            motion = seg.motion if seg.motion is not None else (
                0.0 if prev is None else abs(hip - prev[1]) + abs(angle - prev[0]) / 300)
            prev = (angle, hip)
            yield t, seg, angle, hip, motion, (seg.say if i == 0 else None)
            t += 1 / FPS
