"""Hub: the single pipeline every input goes through.

  browser/server camera or demo → Observation → FallDetector + InactivityMonitor ┐
  simulated / device vitals     → VitalsMonitor                               ├→ SafetyEngine → Database → snapshot
  medication clock              → MedScheduler                                ┘
  user chat / voice             → conversation.route() → engine | meds | wellness | AIAnswers (Claude / offline KB)

One lock guards everything because camera, demo, tick and HTTP threads all call in.
The LLM call is the only slow step and runs OUTSIDE the lock so monitoring never stalls.
"""

import datetime as dt
import threading
import time
from typing import Optional

from . import conversation, daily_checkin, demo_scenarios
from .ai_answers import AIAnswers
from .config import Settings
from .config import settings as default_settings
from .data_types import Detection, Event, Observation
from .database import Database
from .demo_history import seed_history
from .fall_detector import FallDetector
from .inactivity import InactivityMonitor
from .medications import MedScheduler, adherence
from .pose import observation_from_points
from .safety_engine import SafetyEngine
from .telegram_alerts import Notifier
from .vitals import VitalsMonitor, VitalsSimulator


def _hhmm(t: float) -> str:
    return dt.datetime.fromtimestamp(t).strftime("%H:%M")


class Hub:
    def __init__(
        self,
        cfg: Settings = default_settings,
        store: Optional[Database] = None,
        brain: Optional[AIAnswers] = None,
        notifier: Optional[Notifier] = None,
    ):
        self.cfg = cfg
        self.store = store or Database(cfg.db_path)
        self.brain = brain or AIAnswers(cfg)
        self.notifier = notifier or Notifier(cfg)
        self.lock = threading.RLock()
        self._demo_stop = threading.Event()
        self._build()

    def _build(self):
        now = time.time()
        self.detector = FallDetector(self.cfg)
        self.engine = SafetyEngine(self.cfg, next_id=self.store.max_incident_id() + 1)
        self.inactivity = InactivityMonitor(self.store, self.cfg)
        self.vitals = VitalsMonitor(self.cfg)
        self.sim = VitalsSimulator()
        self.meds = MedScheduler(self.store, self.cfg, now)
        if self.cfg.seed_history:
            seed_history(self.store, self.meds, now)
        self.last_obs: Optional[Observation] = None
        self.demo_name: Optional[str] = None
        self.chat: list[dict] = []
        self._msg_id = 0
        self.version = 0
        self._vitals_t = 0.0
        self._vitals_saved_t = 0.0
        self.sim_active = self.cfg.vitals_sim  # simulated vitals stream: config, or briefly during a demo
        self.browser = {"connected": 0, "fps": 0.0, "last_t": 0.0, "_n": 0, "_t": now}

    # ---------- camera (body pose from the browser) ----------
    def ingest(self, obs: Observation):
        with self.lock:
            if self.demo_name and obs.source == "camera":
                return  # while a demo runs, ignore the camera so streams don't mix
            self.last_obs = obs
            self.version += 1
            for det in (self.detector.update(obs), self.inactivity.update(obs)):
                if det:
                    self._detect(det, obs.t)

    def ingest_points(self, points: Optional[list], motion: Optional[float]) -> dict:
        """One browser frame (landmarks only, never pixels). Returns what the server understood."""
        now = time.time()
        obs = observation_from_points(points, now, motion)
        with self.lock:
            b = self.browser
            b["last_t"], b["_n"] = now, b["_n"] + 1
            if now - b["_t"] >= 1:
                b["fps"], b["_n"], b["_t"] = round(b["_n"] / (now - b["_t"]), 1), 0, now
        self.ingest(obs)
        return {
            "person": obs.person,
            "posture": obs.posture,
            "torso_angle": round(obs.torso_angle),
            "full_body": obs.full_body,
            "state": self.engine.state,
        }

    def _detect(self, det: Detection, t: float):
        events = self.engine.on_detection(det, t)
        self._record(events)
        if any(e.kind == "checkin_sent" for e in events):
            self._say("assistant", self.engine.pending_prompt, kind="checkin")

    # ---------- user ----------
    def user_message(self, text: str) -> dict:
        with self.lock:
            now = time.time()
            self._say("user", text)
            lang = conversation.wants_lang(text, self.engine.lang)
            self.engine.lang = lang
            flags = daily_checkin.red_flags(text)
            in_checkin = bool(self.engine.pending_deadline())
            if flags and not conversation.is_question(text):
                route = "red_flag"  # emergency words win even during a check-in
            else:
                route = conversation.route(text, in_checkin, bool(flags))

            if route in ("checkin_reply", "help"):
                reply, events = self.engine.on_user_message(text, now)
                self._record(events)
                return self._answer(reply, route)
            if route == "red_flag":
                self._record([Event(now, "user_message", text, "user")])
                self._record(self.engine.report_red_flag(flags, text, now))
                return self._answer(conversation.REPLIES["red_flag"][lang], route, kind="alert")
            if route == "med_taken":
                return self._answer(self._take_med(now, lang=lang), route)
            if route == "med_snooze":
                res = self.meds.snooze(now)
                if res:
                    self._record(
                        [
                            Event(
                                now,
                                "med_snoozed",
                                f"{res[1].name} snoozed for {self.cfg.med_snooze_s / 60:.0f} min",
                                "user",
                            )
                        ]
                    )
                    return self._answer(
                        (
                            "Baik, saya akan ingatkan semula dalam {m} minit."
                            if lang == "ms"
                            else "Okay, I'll remind you again in {m} minutes."
                        ).format(m=round(self.cfg.med_snooze_s / 60)),
                        route,
                    )
                return self._answer(conversation.REPLIES["med_none"][lang], route)
            if route == "med_schedule":
                return self._answer(self._next_med_text(now, lang), route)
            if route == "wellness":
                return self._answer(
                    "Mari buat semakan harian. Isi kad di skrin."
                    if lang == "ms"
                    else "Let's do your daily check-in. Please fill in the card on screen.",
                    route,
                    action="open_wellness",
                )
            context, history = self._context_text(now), [m for m in self.chat[:-1] if m["from"] != "system"]
            profile = self.profile()

        res = self.brain.answer(text, lang, context, history, profile)  # slow: outside the lock
        with self.lock:
            return self._answer(res["reply"], "ask", source=res["source"], refs=res["refs"])

    def _answer(
        self,
        reply: str,
        route: str,
        source: str = "rules",
        kind: str = "chat",
        action: Optional[str] = None,
        refs: Optional[list] = None,
    ) -> dict:
        self._say("assistant", reply, kind=kind, source=source, refs=refs)
        return {"reply": reply, "route": route, "source": source, "action": action, "refs": refs or []}

    def take_med(self, med_id: Optional[str] = None) -> dict:
        with self.lock:
            text = self._take_med(time.time(), med_id, self.engine.lang)
            self._say("assistant", text)
            return {"reply": text}

    def _take_med(self, now: float, med_id: Optional[str] = None, lang: str = "en") -> str:
        res = self.meds.take(now, med_id)
        if not res:
            return conversation.REPLIES["med_none"][lang]
        dose, med = res
        self._record(
            [Event(now, "med_taken", f"{med.name} {med.dose} taken (due {_hhmm(dose.due_t)})", "user")]
        )
        return (
            f"Bagus! {med.name} {med.dose} direkodkan diambil pada {_hhmm(now)}."
            if lang == "ms"
            else f"Great! I've recorded your {med.name} {med.dose} as taken at {_hhmm(now)}."
        )

    def _next_med_text(self, now: float, lang: str) -> str:
        nxt = self.meds.next_dose(now)
        if not nxt:
            return "Tiada ubat dijadualkan." if lang == "ms" else "You have no medicines scheduled."
        when = _hhmm(nxt["due_t"])
        return (
            f"Ubat seterusnya: {nxt['name']} {nxt['dose']} pada {when}. {nxt['instructions']}"
            if lang == "ms"
            else f"Your next medicine is {nxt['name']} {nxt['dose']} at {when}. {nxt['instructions']}"
        )

    def submit_wellness(self, data: dict) -> dict:
        with self.lock:
            now = time.time()
            symptoms = [s for s in data.get("symptoms", []) if isinstance(s, str)][:20]
            note = str(data.get("note", ""))[:500]
            lang = data.get("lang") or self.engine.lang
            res = daily_checkin.triage(
                data.get("mood"), data.get("pain"), data.get("sleep_h"), symptoms, note, lang
            )
            self.store.add_record(
                "wellness",
                now,
                {
                    "mood": data.get("mood"),
                    "pain": data.get("pain"),
                    "sleep_h": data.get("sleep_h"),
                    "symptoms": symptoms,
                    "note": note,
                    "level": res["level"],
                    "simulated": False,
                },
            )
            self._record(
                [
                    Event(
                        now,
                        "wellness_checkin",
                        f"Daily check-in: {res['level'].replace('_', ' ')}"
                        + (f" — {'; '.join(res['reasons'])}" if res["reasons"] else ""),
                        "user",
                    )
                ]
            )
            if res["level"] == "emergency":
                self._record(self.engine.report_red_flag(res["red_flags"], note or "daily check-in", now))
                self._say("assistant", " ".join(res["advice"]), kind="alert")
            else:
                self._say("assistant", " ".join(res["advice"]))
            return res

    def add_vitals(self, reading: dict, source: str = "device") -> dict:
        with self.lock:
            now = time.time()
            det = self.vitals.add(reading, now, source)
            self.version += 1
            if det:
                self._detect(det, now)
            return {"ok": True, "alert": bool(det)}

    def pill_check(self, image_b64: str) -> dict:
        with self.lock:
            names, lang = [m.name for m in self.meds.meds.values()], self.engine.lang
        res = self.brain.read_medicine(image_b64, names, lang)
        with self.lock:
            self._record(
                [
                    Event(
                        time.time(),
                        "pill_check",
                        f"Pill check: {res.get('medicine') or 'label not read'}"
                        + (f" (matches {res['matches']})" if res.get("matches") else ""),
                        "assistant",
                    )
                ]
            )
            if res.get("note"):
                self._say("assistant", res["note"])
        return res

    def acknowledge(self, iid: int):
        with self.lock:
            self._record(self.engine.acknowledge(iid, time.time()))

    def resolve(self, iid: int, note: str = ""):
        with self.lock:
            self._record(self.engine.resolve(iid, time.time(), note))

    # ---------- clock (called every 0.5 s) ----------
    def tick(self):
        with self.lock:
            now = time.time()
            timed_out = self.engine.tick(now)
            self._record(timed_out)
            if timed_out:
                self._say(
                    "assistant",
                    (
                        f"Saya tidak dengar balasan, jadi saya telah memaklumkan {self.caregiver_label(self.engine.lang)}. "
                        "Bantuan sedang diminta."
                        if self.engine.lang == "ms"
                        else f"I didn't hear back, so I've alerted {self.caregiver_label(self.engine.lang)}. Help is on the way."
                    ),
                    kind="alert",
                )
            for action, dose, med in self.meds.tick(now):
                if action == "remind":
                    self._record([Event(now, "med_due", f"Reminder: {med.name} {med.dose}", "meds")])
                    self._say(
                        "assistant",
                        conversation.MED_REMINDER[self.engine.lang].format(
                            name=med.name, dose=med.dose, instructions=med.instructions
                        ),
                        kind="reminder",
                    )
                else:
                    grace = dose.grace_s if dose.grace_s is not None else self.cfg.med_grace_s
                    self._detect(
                        Detection(
                            "missed_medication",
                            now,
                            [
                                f"{med.name} {med.dose} due at {_hhmm(dose.due_t)} was not confirmed within "
                                f"{grace / 60:.0f} min"
                                if grace >= 120
                                else f"{med.name} {med.dose} due at {_hhmm(dose.due_t)} was not confirmed within {grace:.0f}s"
                            ],
                            "The person may have taken it without telling me.",
                            "meds",
                        ),
                        now,
                    )
            if self.sim_active and now - self._vitals_t >= self.cfg.vitals_interval_s:
                self._vitals_t = now
                det = self.vitals.add(self.sim.next(), now, "simulated")
                self.version += 1
                if det:
                    self._detect(det, now)
            latest = self.vitals.latest()
            if latest and now - self._vitals_saved_t >= 300:
                self._vitals_saved_t = now
                self.store.add_record(
                    "vitals_daily",
                    now,
                    {
                        **{k: latest.get(k) for k in ("hr", "spo2", "sys", "dia", "temp")},
                        "simulated": latest["source"] == "simulated",
                    },
                )
            self.inactivity.tick(now)

    # ---------- demo ----------
    def start_demo(self, name: str):
        if name not in demo_scenarios.SCENARIOS:
            raise KeyError(name)
        self.stop_demo()
        with self.lock:
            self.detector.reset()
            self.inactivity.reset()
            self.demo_name = name
            self._demo_stop = threading.Event()  # fresh event per run: old threads keep their own
            setup = demo_scenarios.SCENARIOS[name].get("setup", {})
            if "inactivity_s" in setup:
                self.inactivity.override_s = setup["inactivity_s"]
            if "dose_grace_s" in setup:
                self.meds.demo_dose(time.time(), setup["dose_grace_s"])
            if "vitals" in setup:
                self.sim.mode = setup["vitals"]
                self.sim_active = True
            self._record(
                [
                    Event(
                        time.time(),
                        "demo_started",
                        f"SIMULATED scenario started: {demo_scenarios.SCENARIOS[name]['label']}",
                        "demo",
                    )
                ]
            )
        threading.Thread(target=self._run_demo, args=(name, self._demo_stop), daemon=True).start()

    def stop_demo(self):
        self._demo_stop.set()
        with self.lock:
            if self.demo_name:
                self._end_demo()

    def _end_demo(self):
        self.demo_name = None
        self.detector.reset()
        self.inactivity.reset()
        self.inactivity.override_s = None
        self.sim.mode = "normal"
        self.sim_active = self.cfg.vitals_sim
        self.meds.clear_demo()
        self.version += 1

    def _run_demo(self, name: str, stop: threading.Event):
        start = time.time()
        for offset, seg, angle, hip, motion, say in demo_scenarios.frames(
            demo_scenarios.SCENARIOS[name]["steps"]
        ):
            if stop.wait(max(0.0, start + offset - time.time())):
                return
            self.ingest(Observation(time.time(), seg.person, angle, hip, seg.posture, "demo", motion=motion))
            if say:
                self.user_message(say)
        with self.lock:
            if not stop.is_set():
                self._end_demo()

    def reset(self):
        self.stop_demo()
        with self.lock:
            self.store.clear()
            self._build()
            self.version += 1

    # ---------- output ----------
    def snapshot(self) -> dict:
        with self.lock:
            now = time.time()
            o = self.last_obs
            live_ok = o is not None and now - o.t < 2
            r = self.inactivity
            return {
                "version": self.version,
                "server_time": now,
                "state": self.engine.state,
                "active_incident": self.engine.active.dict() if self.engine.active else None,
                "incidents": self.store.recent_incidents(),
                "events": self.store.recent_events(60),
                "chat": self.chat[-30:],
                "pending_prompt": self.engine.pending_prompt,
                "checkin_deadline": self.engine.pending_deadline(),
                "lang": self.engine.lang,
                "camera": {
                    "browser_connected": self.browser["connected"] > 0,
                    "browser_fps": self.browser["fps"] if now - self.browser["last_t"] < 3 else 0,
                },
                "demo": {
                    "running": self.demo_name,
                    "scenarios": {k: v["label"] for k, v in demo_scenarios.SCENARIOS.items()},
                },
                "live": {
                    "person": o.person,
                    "posture": o.posture,
                    "torso_angle": round(o.torso_angle),
                    "source": o.source,
                    "motion": o.motion,
                }
                if live_ok
                else None,
                "routine": {
                    "still_s": round(now - r.still_since) if r.still_since else 0,
                    "threshold_s": round(r.threshold(now)),
                },
                "meds": {
                    "today": self.meds.today(now),
                    "next": self.meds.next_dose(now),
                    "schedule": self.meds.schedule(),
                },
                "vitals": {
                    "latest": self.vitals.latest(),
                    "history": self.vitals.history(90),
                    "simulated": self.sim_active,
                    "mode": self.sim.mode,
                },
                "ai": {
                    "online": self.brain.online,
                    "model": self.cfg.anthropic_model if self.brain.online else None,
                },
                "notify": {"telegram": self.notifier.enabled},
                "profile": self.profile(),
                "config": {"checkin_timeout_s": self.cfg.checkin_timeout_s},
            }

    def insights(self, days: int = 7) -> dict:
        with self.lock:
            now = time.time()
            since = now - days * 86400
            incidents = self.store.recent_incidents(200)
            by_kind: dict[str, int] = {}
            for i in incidents:
                if i["created_t"] >= since:
                    by_kind[i["kind"]] = by_kind.get(i["kind"], 0) + 1
            return {
                "generated_t": now,
                "profile": self.profile(),
                "adherence": adherence(self.store, now, days),
                "activity": self.inactivity.heatmap(now, days),
                "wellness": self.store.records("wellness", since=since),
                "vitals": self.store.records("vitals_daily", since=since),
                "incidents": [i for i in incidents if i["created_t"] >= since],
                "incident_counts": by_kind,
                "meds": self.meds.schedule(),
                "events": self.store.recent_events(200, since=since),
            }

    # ---------- profile (entered by the user/caregiver; nothing is invented) ----------
    PROFILE_FIELDS = {
        "user_name": 60,
        "caregiver_name": 60,
        "caregiver_phone": 30,
        "conditions": 300,
        "allergies": 200,
    }

    def profile(self) -> dict:
        saved = self.store.kv_get("profile") or {}
        defaults = {"user_name": self.cfg.user_name, "caregiver_name": self.cfg.caregiver_name}
        return {k: str(saved.get(k, defaults.get(k, ""))) for k in self.PROFILE_FIELDS}

    def set_profile(self, data: dict) -> dict:
        with self.lock:
            p = self.profile()
            for k, limit in self.PROFILE_FIELDS.items():
                if k in data and data[k] is not None:
                    p[k] = str(data[k]).strip()[:limit]
            self.store.kv_set("profile", p)
            self.version += 1
            return p

    def caregiver_label(self, lang: str = "en") -> str:
        return self.profile()["caregiver_name"] or ("penjaga anda" if lang == "ms" else "your caregiver")

    def _context_text(self, now: float) -> str:
        """ONLY facts the app actually holds. Missing facts are stated as missing so the AI can't fill them in."""
        p = self.profile()
        meds = "; ".join(
            f"{m.name} {m.dose} at {'/'.join(m.times) or 'no set time'}"
            + (f" (purpose noted: {m.purpose})" if m.purpose else "")
            for m in self.meds.meds.values()
        )
        lines = [
            f"Medicines on their schedule: {meds or 'none entered in the app'}",
            f"Health conditions noted by the user/caregiver: {p['conditions'] or 'none entered'}",
            f"Allergies noted: {p['allergies'] or 'none entered'}",
        ]
        nxt = self.meds.next_dose(now)
        if nxt:
            lines.append(f"Next dose: {nxt['name']} at {_hhmm(nxt['due_t'])} ({nxt['status']})")
        v = self.vitals.latest()
        if v:
            parts = [
                f"{label} {v[k]}{unit}"
                for k, label, unit in (
                    ("hr", "heart rate", " bpm"),
                    ("spo2", "SpO2", "%"),
                    ("temp", "temperature", "°C"),
                )
                if k in v
            ]
            if "sys" in v and "dia" in v:
                parts.append(f"BP {v['sys']}/{v['dia']} mmHg")
            age = round((now - v["t"]) / 60)
            lines.append(
                f"Latest reading ({'SIMULATED demo data' if v['source'] == 'simulated' else v['source']}, "
                f"{age} min ago): " + ", ".join(parts)
            )
        else:
            lines.append("Vital-sign readings: none recorded")
        lines.append(f"Current time: {dt.datetime.fromtimestamp(now).strftime('%A %H:%M')}")
        return "\n".join(lines)

    # ---------- helpers ----------
    def _record(self, events: list[Event]):
        if not events:
            return
        for e in events:
            self.store.add_event(e)
            if e.kind in ("escalated", "caregiver_notice"):
                icon = "🚨" if e.kind == "escalated" else "ℹ️"
                self.notifier.send(
                    f"{icon} Kawan — {self.profile()['user_name'] or 'your family member'}: {e.message}"
                )
        for inc in self.engine.incidents.values():
            self.store.save_incident(inc)
        self.version += 1

    def _say(
        self,
        who: str,
        text: Optional[str],
        kind: str = "chat",
        source: Optional[str] = None,
        refs: Optional[list] = None,
    ):
        if not text:
            return
        self._msg_id += 1
        self.chat.append(
            {
                "id": self._msg_id,
                "t": time.time(),
                "from": who,
                "text": text,
                "kind": kind,
                "source": source,
                "refs": refs or [],
            }
        )
        self.chat = self.chat[-100:]
        self.version += 1
