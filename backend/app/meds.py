"""Medication reminders. Deterministic, time-injected, persisted.

Each scheduled dose moves through:
    upcoming → due (reminder spoken) → taken
                                   ↘ snoozed → due again
                                   ↘ missed  (after the grace window → caregiver notice)
"""
import datetime as dt
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from .config import Settings, settings as default_settings
from .store import Store

DEFAULT_MEDS = [
    {"name": "Metformin", "dose": "500 mg", "times": ["08:00", "20:00"], "instructions": "Take with food.",
     "purpose": "Helps control blood sugar (type 2 diabetes)", "color": "#5b8def"},
    {"name": "Amlodipine", "dose": "5 mg", "times": ["09:00"], "instructions": "Same time every day.",
     "purpose": "Lowers blood pressure", "color": "#f2a541"},
    {"name": "Atorvastatin", "dose": "20 mg", "times": ["21:00"], "instructions": "Take in the evening.",
     "purpose": "Lowers cholesterol", "color": "#47b39d"},
]


@dataclass
class Med:
    id: str
    name: str
    dose: str
    times: list[str]
    instructions: str = ""
    purpose: str = ""
    color: str = "#5b8def"


@dataclass
class Dose:
    id: str
    med_id: str
    due_t: float
    status: str = "upcoming"          # upcoming | due | snoozed | taken | missed
    grace_s: Optional[float] = None   # per-dose override (demo); else cfg.med_grace_s
    reminded_t: Optional[float] = None
    snooze_until: Optional[float] = None
    taken_t: Optional[float] = None
    demo: bool = False
    history: list[str] = field(default_factory=list)


def _at(day: dt.date, hhmm: str) -> float:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m)).timestamp()


class MedScheduler:
    def __init__(self, store: Store, cfg: Settings = default_settings, now: Optional[float] = None):
        import time
        self.cfg, self.store = cfg, store
        now = time.time() if now is None else now
        saved = store.kv_get("meds")
        if saved is None:
            saved = [{"id": uuid.uuid4().hex[:8], **m} for m in DEFAULT_MEDS]
            store.kv_set("meds", saved)
        self.meds: dict[str, Med] = {m["id"]: Med(**m) for m in saved}
        self.start_t = store.kv_get("meds_start_t") or now   # never invent doses from before we started
        store.kv_set("meds_start_t", self.start_t)
        self.doses: dict[str, Dose] = {}
        for r in store.records("dose", since=now - 2 * 86400):   # survive restarts: don't re-remind
            if not r.get("demo"):
                did = f"{r['med_id']}@{r['t']:.0f}"
                self.doses[did] = Dose(did, r["med_id"], r["t"], r["status"], taken_t=r.get("taken_t"))

    # ---------- schedule management ----------
    def add_med(self, data: dict) -> Med:
        med = Med(id=uuid.uuid4().hex[:8], name=data["name"].strip()[:60], dose=data.get("dose", "").strip()[:30],
                  times=sorted({t for t in data.get("times", []) if _valid_time(t)}),
                  instructions=data.get("instructions", "")[:200], purpose=data.get("purpose", "")[:200],
                  color=data.get("color", "#5b8def"))
        self.meds[med.id] = med
        self._save()
        return med

    def remove_med(self, med_id: str):
        self.meds.pop(med_id)
        self.doses = {k: d for k, d in self.doses.items() if d.med_id != med_id or d.status in ("taken", "missed")}
        self._save()

    def _save(self):
        self.store.kv_set("meds", [asdict(m) for m in self.meds.values()])

    # ---------- clock ----------
    def tick(self, now: float) -> list[tuple[str, Dose, Med]]:
        """Advance every dose. Returns actions for the hub: ("remind" | "missed", dose, med)."""
        self._ensure_doses(now)
        actions = []
        for d in sorted(self.doses.values(), key=lambda d: d.due_t):
            med = self.meds.get(d.med_id)
            if med is None or d.status in ("taken", "missed"):
                continue
            grace = d.grace_s if d.grace_s is not None else self.cfg.med_grace_s
            if now >= d.due_t + grace:
                d.status = "missed"
                d.history.append(f"missed@{now:.0f}")
                self._finalise(d, med)
                actions.append(("missed", d, med))
            elif d.status == "upcoming" and now >= d.due_t:
                d.status, d.reminded_t = "due", now
                actions.append(("remind", d, med))
            elif d.status == "snoozed" and now >= (d.snooze_until or 0):
                d.status, d.reminded_t = "due", now
                actions.append(("remind", d, med))
            elif d.status == "due" and d.reminded_t and now - d.reminded_t >= self.cfg.med_remind_again_s:
                d.reminded_t = now
                actions.append(("remind", d, med))
        return actions

    def _ensure_doses(self, now: float):
        today = dt.date.fromtimestamp(now)
        for day in (today, today + dt.timedelta(days=1)):
            for med in self.meds.values():
                for hhmm in med.times:
                    due = _at(day, hhmm)
                    did = f"{med.id}@{due:.0f}"
                    if due >= self.start_t and did not in self.doses:
                        self.doses[did] = Dose(did, med.id, due)
        # forget finished doses older than 2 days (they are in the records table)
        self.doses = {k: d for k, d in self.doses.items()
                      if not (d.status in ("taken", "missed") and d.due_t < now - 2 * 86400)}

    # ---------- user actions ----------
    def take(self, now: float, med_id: Optional[str] = None) -> Optional[tuple[Dose, Med]]:
        """Mark the most relevant dose as taken: an overdue one first, else one due within the next hour."""
        self._ensure_doses(now)
        cands = [d for d in self.doses.values() if (med_id is None or d.med_id == med_id) and d.med_id in self.meds]
        due = sorted((d for d in cands if d.status in ("due", "snoozed")), key=lambda d: d.due_t)
        early = sorted((d for d in cands if d.status == "upcoming" and d.due_t - now <= 3600), key=lambda d: d.due_t)
        pick = (due or early or [None])[0]
        if pick is None:
            return None
        pick.status, pick.taken_t = "taken", now
        pick.history.append(f"taken@{now:.0f}")
        med = self.meds[pick.med_id]
        self._finalise(pick, med)
        return pick, med

    def snooze(self, now: float) -> Optional[tuple[Dose, Med]]:
        due = sorted((d for d in self.doses.values() if d.status == "due"), key=lambda d: d.due_t)
        if not due:
            return None
        d = due[0]
        d.status, d.snooze_until = "snoozed", now + self.cfg.med_snooze_s
        d.history.append(f"snoozed@{now:.0f}")
        return d, self.meds[d.med_id]

    def demo_dose(self, now: float, grace_s: float) -> Dose:
        """SIMULATED: a dose of the first medicine that is due right now with a short grace window."""
        med = next(iter(self.meds.values()))
        d = Dose(f"{med.id}@demo{now:.0f}", med.id, now, grace_s=grace_s, demo=True)
        self.doses[d.id] = d
        return d

    def clear_demo(self):
        self.doses = {k: d for k, d in self.doses.items() if not d.demo or d.status in ("taken", "missed")}

    # ---------- views ----------
    def _finalise(self, d: Dose, med: Med):
        self.store.add_record("dose", d.due_t, {"med_id": med.id, "name": med.name, "dose": med.dose,
                                                "status": d.status, "taken_t": d.taken_t, "demo": d.demo,
                                                "simulated": d.demo})

    def today(self, now: float) -> list[dict]:
        self._ensure_doses(now)
        start = _at(dt.date.fromtimestamp(now), "00:00")
        out = []
        for d in sorted(self.doses.values(), key=lambda d: d.due_t):
            med = self.meds.get(d.med_id)
            if med and start <= d.due_t < start + 86400:
                out.append({"id": d.id, "med_id": med.id, "name": med.name, "dose": med.dose, "color": med.color,
                            "instructions": med.instructions, "due_t": d.due_t, "status": d.status,
                            "taken_t": d.taken_t, "demo": d.demo})
        return out

    def next_dose(self, now: float) -> Optional[dict]:
        upcoming = [d for d in self.today(now) + self._tomorrow(now) if d["status"] in ("upcoming", "due", "snoozed")]
        return upcoming[0] if upcoming else None

    def _tomorrow(self, now: float) -> list[dict]:
        return self.today(now + 86400)

    def schedule(self) -> list[dict]:
        return [asdict(m) for m in self.meds.values()]


def adherence(store: Store, now: float, days: int = 7) -> dict:
    """Per-day taken/missed counts plus overall %, from finalised dose records."""
    today = dt.date.fromtimestamp(now)
    start = _at(today - dt.timedelta(days=days - 1), "00:00")
    per_day: dict[str, dict] = {}
    for i in range(days):
        day = today - dt.timedelta(days=days - 1 - i)
        per_day[day.isoformat()] = {"date": day.isoformat(), "taken": 0, "missed": 0, "simulated": False}
    for r in store.records("dose", since=start):
        key = dt.date.fromtimestamp(r["t"]).isoformat()
        if key in per_day and r["status"] in ("taken", "missed"):
            per_day[key][r["status"]] += 1
            per_day[key]["simulated"] |= bool(r.get("simulated"))
    taken = sum(d["taken"] for d in per_day.values())
    missed = sum(d["missed"] for d in per_day.values())
    return {"days": list(per_day.values()), "taken": taken, "missed": missed,
            "percent": round(100 * taken / (taken + missed)) if taken + missed else None}


def _valid_time(t: str) -> bool:
    try:
        h, m = (int(x) for x in t.split(":"))
        return 0 <= h < 24 and 0 <= m < 60
    except (ValueError, AttributeError):
        return False
