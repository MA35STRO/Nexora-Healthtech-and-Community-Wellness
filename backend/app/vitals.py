"""Vital signs: a SIMULATED home-device stream + real readings via POST /api/vitals, with explainable rules.

Rules need *sustained* abnormal values (one bad reading from a loose finger clip is not an alert),
except blood-pressure crisis range, which a single reading is enough to flag for a check-in.
Thresholds are general adult screening values — not personalised clinical targets.
"""
import random
from collections import deque
from typing import Optional

from .config import Settings, settings as default_settings
from .models import Detection

FIELDS = ("hr", "spo2", "sys", "dia", "temp")


class VitalsSimulator:
    """Plausible resting adult vitals with slow drift. `mode` lets demos inject a deterioration."""

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self.v = {"hr": 74.0, "spo2": 97.0, "sys": 128.0, "dia": 82.0, "temp": 36.7}
        self.mode = "normal"   # normal | hypoxia | tachycardia | fever | crisis

    def next(self) -> dict:
        r, v = self.rng, self.v
        target = {"hr": 74, "spo2": 97, "sys": 128, "dia": 82, "temp": 36.7}
        if self.mode == "hypoxia":
            target.update(spo2=88, hr=104)
        elif self.mode == "tachycardia":
            target.update(hr=132)
        elif self.mode == "fever":
            target.update(temp=38.9, hr=98)
        elif self.mode == "crisis":
            target.update(sys=186, dia=122)
        speed = 0.35 if self.mode != "normal" else 0.08
        for k, noise in (("hr", 1.5), ("spo2", 0.35), ("sys", 1.5), ("dia", 1.0), ("temp", 0.03)):
            v[k] += (target[k] - v[k]) * speed + r.gauss(0, noise)
        v["spo2"] = min(100.0, v["spo2"])
        return {"hr": round(v["hr"]), "spo2": round(v["spo2"]), "sys": round(v["sys"]), "dia": round(v["dia"]),
                "temp": round(v["temp"], 1)}


class VitalsMonitor:
    def __init__(self, cfg: Settings = default_settings):
        self.cfg = cfg
        self.readings: deque[dict] = deque(maxlen=600)
        self.cooldown: dict[str, float] = {}

    def reset(self):
        self.readings.clear()
        self.cooldown.clear()

    def latest(self) -> Optional[dict]:
        return self.readings[-1] if self.readings else None

    def add(self, reading: dict, t: float, source: str) -> Optional[Detection]:
        r = {"t": t, "source": source, **{k: reading[k] for k in FIELDS if reading.get(k) is not None}}
        self.readings.append(r)
        return self._check(t, source)

    def _sustained(self, key: str, bad, t: float) -> bool:
        window = [r for r in self.readings if t - r["t"] <= self.cfg.vitals_sustain_s and key in r]
        span = window[-1]["t"] - window[0]["t"] if len(window) > 1 else 0
        return len(window) >= 3 and span >= self.cfg.vitals_sustain_s * 0.8 and all(bad(r[key]) for r in window)

    def _check(self, t: float, source: str) -> Optional[Detection]:
        c, s = self.cfg, f"{self.cfg.vitals_sustain_s:.0f}s"
        rules = [
            ("spo2_low", lambda: self._sustained("spo2", lambda x: x < c.spo2_low, t),
             lambda: f"Blood oxygen (SpO2) below {c.spo2_low:.0f}% for {s} (now {self.latest()['spo2']}%)"),
            ("hr_high", lambda: self._sustained("hr", lambda x: x > c.hr_high, t),
             lambda: f"Resting heart rate above {c.hr_high:.0f} bpm for {s} (now {self.latest()['hr']} bpm)"),
            ("hr_low", lambda: self._sustained("hr", lambda x: x < c.hr_low, t),
             lambda: f"Heart rate below {c.hr_low:.0f} bpm for {s} (now {self.latest()['hr']} bpm)"),
            ("bp_crisis", lambda: (lambda r: r.get("sys", 0) >= c.sys_crisis or r.get("dia", 0) >= c.dia_crisis)(self.latest()),
             lambda: f"Blood pressure in crisis range ({self.latest().get('sys')}/{self.latest().get('dia')} mmHg)"),
            ("fever", lambda: self._sustained("temp", lambda x: x >= c.temp_fever, t),
             lambda: f"Temperature at or above {c.temp_fever}°C for {s} (now {self.latest()['temp']}°C)"),
        ]
        reasons = []
        for name, hit, why in rules:
            try:
                fired = hit()
            except KeyError:
                fired = False
            if fired and t >= self.cooldown.get(name, 0):
                self.cooldown[name] = t + 600   # same rule won't re-fire for 10 min
                reasons.append(why())
        if not reasons:
            return None
        sim = "SIMULATED readings. " if source == "simulated" else ""
        return Detection("vitals_alert", t, reasons,
                         sim + "Home devices can misread (loose clip, movement, cold fingers). User check-in required.",
                         "vitals")

    def history(self, n: int = 90) -> list[dict]:
        return list(self.readings)[-n:]
