"""Routine monitor: learns how long the person is usually still at each hour, flags unusual inactivity.

Inactivity = the person is IN VIEW but has not moved for longer than
    max(INACTIVITY_MIN_S, INACTIVITY_K × typical longest still period for this hour)   (capped)
and only during waking hours, so normal sleep is never flagged. Out of view = can't judge = no alert.
It also keeps per-hour presence/activity minutes for the caregiver heatmap.
"""
import datetime as dt
from typing import Optional

from .config import Settings, settings as default_settings
from .models import Detection, Observation
from .store import Store

BASELINE_KEEP = 30   # still-period samples remembered per hour


def _p90(xs: list[float]) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(0.9 * len(s)))] if s else 0.0


class RoutineMonitor:
    def __init__(self, store: Store, cfg: Settings = default_settings):
        self.cfg, self.store = cfg, store
        self.baseline: dict[str, list[float]] = store.kv_get("still_baseline", {})
        self.override_s: Optional[float] = None   # demo: short threshold, ignores waking hours
        self.last_t: Optional[float] = None
        self.still_since: Optional[float] = None
        self.flagged = False
        self.day: Optional[str] = None
        self.hours: list[dict] = []
        self._dirty_t = 0.0

    def reset(self):
        self.still_since, self.flagged, self.last_t = None, False, None

    # ---------- learning ----------
    def threshold(self, t: float) -> float:
        if self.override_s is not None:
            return self.override_s
        typical = _p90(self.baseline.get(str(dt.datetime.fromtimestamp(t).hour), []))
        return min(self.cfg.inactivity_max_s, max(self.cfg.inactivity_min_s, self.cfg.inactivity_k * typical))

    def _learn(self, t: float, still_s: float):
        if still_s < 30:
            return
        h = str(dt.datetime.fromtimestamp(t).hour)
        self.baseline[h] = (self.baseline.get(h, []) + [round(still_s)])[-BASELINE_KEEP:]
        self.store.kv_set("still_baseline", self.baseline)

    def awake_hours(self, t: float) -> bool:
        h = dt.datetime.fromtimestamp(t).hour + dt.datetime.fromtimestamp(t).minute / 60
        return self.cfg.waking_start_h <= h < self.cfg.waking_end_h

    # ---------- per frame ----------
    def update(self, obs: Observation) -> Optional[Detection]:
        gap = 0.0 if self.last_t is None else max(0.0, min(1.0, obs.t - self.last_t))
        self.last_t = obs.t
        self._account(obs, gap)
        if not obs.person or obs.motion is None:
            if self.still_since is not None and not obs.person:
                self._learn(obs.t, obs.t - self.still_since)
            self.still_since, self.flagged = None, False   # out of view: we can't judge stillness
            return None

        if obs.motion >= self.cfg.motion_threshold:
            if self.still_since is not None:
                self._learn(obs.t, obs.t - self.still_since)
            self.still_since, self.flagged = None, False
            return None

        if self.still_since is None:
            self.still_since = obs.t
        still = obs.t - self.still_since
        limit = self.threshold(obs.t)
        if self.flagged or still < limit or (self.override_s is None and not self.awake_hours(obs.t)):
            return None

        self.flagged = True
        reasons = [f"No movement for {_dur(still)} while {obs.posture} and in view of the camera"]
        typical = _p90(self.baseline.get(str(dt.datetime.fromtimestamp(obs.t).hour), []))
        if typical and self.override_s is None:
            reasons.append(f"Usually still for at most ~{_dur(typical)} at this time of day (learned)")
        reasons.append(f"Threshold for this hour: {_dur(limit)}")
        return Detection("inactivity", obs.t, reasons,
                         "Could simply be resting, reading or napping. User check-in required.", obs.source)

    def tick(self, now: float):
        if self.last_t is not None and now - self.last_t > 5:   # no frames (camera off) → can't judge
            self.still_since, self.flagged = None, False
        if now - self._dirty_t > 30:
            self.flush()
            self._dirty_t = now

    # ---------- activity heatmap ----------
    def _account(self, obs: Observation, gap: float):
        d = dt.datetime.fromtimestamp(obs.t)
        key = d.date().isoformat()
        if key != self.day:
            self.flush()
            self.day = key
            saved = self.store.kv_get(f"activity:{key}")
            self.hours = saved["hours"] if saved else [{"present": 0.0, "active": 0.0} for _ in range(24)]
        if obs.person and obs.source != "demo":
            self.hours[d.hour]["present"] += gap
            if obs.motion is not None and obs.motion >= self.cfg.motion_threshold:
                self.hours[d.hour]["active"] += gap

    def flush(self):
        if self.day:
            self.store.kv_set(f"activity:{self.day}", {"hours": self.hours, "simulated": False})

    def heatmap(self, now: float, days: int = 7) -> list[dict]:
        self.flush()
        out = []
        today = dt.date.fromtimestamp(now)
        for i in range(days - 1, -1, -1):
            day = (today - dt.timedelta(days=i)).isoformat()
            rec = self.store.kv_get(f"activity:{day}") or {"hours": [{"present": 0, "active": 0}] * 24}
            out.append({"date": day, "simulated": rec.get("simulated", False),
                        "active_min": [round(h["active"] / 60, 1) for h in rec["hours"]],
                        "present_min": [round(h["present"] / 60, 1) for h in rec["hours"]]})
        return out


def _dur(s: float) -> str:
    return f"{s:.0f}s" if s < 120 else f"{s / 60:.0f} min"
