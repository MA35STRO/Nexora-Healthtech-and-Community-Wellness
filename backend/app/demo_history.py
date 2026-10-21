"""OPTIONAL simulated 6-day history for demos (off by default; enable with SEED_DEMO_HISTORY=1).
Every record is tagged simulated=True and the dashboard and report label it as SIMULATED."""

import datetime as dt
import random

from .database import Database
from .medications import DEMO_MEDS, MedScheduler, _at


def seed_history(store: Database, meds: MedScheduler, now: float, days: int = 6):
    if store.kv_get("seeded"):
        return
    if not meds.meds:  # demo mode with an empty schedule: use the example schedule (also SIMULATED)
        for m in DEMO_MEDS:
            meds.add_med(m)
    rng = random.Random(7)
    today = dt.date.fromtimestamp(now)
    rows = []
    for i in range(days, 0, -1):
        day = today - dt.timedelta(days=i)
        # doses: mostly taken, an evening dose missed now and then
        for med in meds.meds.values():
            for hhmm in med.times:
                t = _at(day, hhmm)
                missed = rng.random() < (0.22 if hhmm >= "20:00" else 0.06)
                rows.append(
                    (
                        "dose",
                        t,
                        {
                            "med_id": med.id,
                            "name": med.name,
                            "dose": med.dose,
                            "status": "missed" if missed else "taken",
                            "taken_t": None if missed else t + rng.randint(60, 1500),
                            "demo": False,
                            "simulated": True,
                        },
                    )
                )
        # wellness check-in each morning
        mood = rng.choice([3, 4, 4, 4, 5, 3, 2])
        rows.append(
            (
                "wellness",
                _at(day, "09:30"),
                {
                    "mood": mood,
                    "pain": rng.choice([1, 2, 2, 3, 4]),
                    "sleep_h": round(rng.uniform(5, 8), 1),
                    "symptoms": rng.choice([[], [], ["tired"], ["dizzy"], ["poor_sleep"]]),
                    "note": "",
                    "level": "self_care",
                    "simulated": True,
                },
            )
        )
        # vitals: 4 readings a day
        for hhmm in ("08:00", "13:00", "18:00", "22:00"):
            rows.append(
                (
                    "vitals_daily",
                    _at(day, hhmm),
                    {
                        "hr": rng.randint(66, 84),
                        "spo2": rng.randint(95, 99),
                        "sys": rng.randint(122, 142),
                        "dia": rng.randint(76, 90),
                        "temp": round(rng.uniform(36.4, 37.1), 1),
                        "simulated": True,
                    },
                )
            )
        # activity heatmap: active in the morning, afternoon nap, quiet evening
        hours = []
        for h in range(24):
            if 7 <= h < 22:
                active = max(
                    0, rng.gauss(22 if h in (8, 9, 10, 17, 18) else 12 if h not in (14, 15) else 4, 4)
                )
                hours.append({"present": 60 * min(60, active + rng.uniform(15, 30)), "active": 60 * active})
            else:
                hours.append({"present": 0.0, "active": 0.0})
        store.kv_set(f"activity:{day.isoformat()}", {"hours": hours, "simulated": True})
    store.add_records(rows)
    store.kv_set("seeded", True)
