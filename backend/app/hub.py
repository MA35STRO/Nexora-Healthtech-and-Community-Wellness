"""Hub: the single pipeline every input goes through.

  browser/server camera or demo → Observation → FallDetector + RoutineMonitor ┐
  simulated / device vitals     → VitalsMonitor                               ├→ ContextEngine → Store → snapshot
  medication clock              → MedScheduler                                ┘
  user chat / voice             → assistant.route() → engine | meds | wellness | Brain (Claude / offline KB)

One lock guards everything because camera, demo, tick and HTTP threads all call in.
The LLM call is the only slow step and runs OUTSIDE the lock so monitoring never stalls.
"""
import datetime as dt
import threading
import time
from typing import Optional

from . import assistant, demo, wellness
from .config import Settings, settings as default_settings
from .detector import FallDetector
from .engine import ContextEngine
from .llm import Brain
from .meds import MedScheduler, adherence
from .models import Detection, Event, Observation
from .notify import Notifier
from .perception import Camera, observation_from_points
from .routine import RoutineMonitor
from .seed import seed_history
from .store import Store
from .vitals import VitalsMonitor, VitalsSimulator


def _hhmm(t: float) -> str:
    return dt.datetime.fromtimestamp(t).strftime("%H:%M")


class Hub:
    def __init__(self, cfg: Settings = default_settings, store: Optional[Store] = None,
                 brain: Optional[Brain] = None, notifier: Optional[Notifier] = None):
        self.cfg = cfg
        self.store = store or Store(cfg.db_path)
        self.brain = brain or Brain(cfg)
        self.notifier = notifier or Notifier(cfg)
        self.lock = threading.RLock()
        self.camera = Camera(cfg.camera_index, cfg.model_path, self.ingest)
        self._demo_stop = threading.Event()
        self._build()

    def _build(self):
        now = time.time()
        self.detector = FallDetector(self.cfg)
        self.engine = ContextEngine(self.cfg, next_id=self.store.max_incident_id() + 1)
        self.routine = RoutineMonitor(self.store, self.cfg)
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
        self.browser = {"connected": 0, "fps": 0.0, "last_t": 0.0, "_n": 0, "_t": now}

    # ---------- perception ----------
    def ingest(self, obs: Observation):
        with self.lock:
            if self.demo_name and obs.source == "camera":
                return   # while a demo runs, ignore the camera so streams don't mix
            self.last_obs = obs
            self.version += 1
            for det in (self.detector.update(obs), self.routine.update(obs)):
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
        return {"person": obs.person, "posture": obs.posture, "torso_angle": round(obs.torso_angle),
                "full_body": obs.full_body, "state": self.engine.state}

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
            lang = assistant.wants_lang(text, self.engine.lang)
            self.engine.lang = lang
            flags = wellness.red_flags(text)
            in_checkin = bool(self.engine.pending_deadline())
            if flags and not assistant.is_question(text):
                route = "red_flag"           # emergency words win even during a check-in
            else:
                route = assistant.route(text, in_checkin, bool(flags))

            if route in ("checkin_reply", "help"):
                reply, events = self.engine.on_user_message(text, now)
                self._record(events)
                return self._answer(reply, route)
            if route == "red_flag":
                self._record([Event(now, "user_message", text, "user")])
                self._record(self.engine.report_red_flag(flags, text, now))
                return self._answer(assistant.REPLIES["red_flag"][lang], route, kind="alert")
            if route == "med_taken":
                return self._answer(self._take_med(now, lang=lang), route)
            if route == "med_snooze":
                res = self.meds.snooze(now)
                if res:
                    self._record([Event(now, "med_snoozed", f"{res[1].name} snoozed for "
                                        f"{self.cfg.med_snooze_s / 60:.0f} min", "user")])
                    return self._answer(("Baik, saya akan ingatkan semula dalam {m} minit." if lang == "ms" else
                                         "Okay, I'll remind you again in {m} minutes.").format(
                                            m=round(self.cfg.med_snooze_s / 60)), route)
                return self._answer(assistant.REPLIES["med_none"][lang], route)
            if route == "med_schedule":
                return self._answer(self._next_med_text(now, lang), route)
            if route == "wellness":
                return self._answer("Mari buat semakan harian. Isi kad di skrin." if lang == "ms" else
                                    "Let's do your daily check-in. Please fill in the card on screen.",
                                    route, action="open_wellness")
            context, history = self._context_text(now), [m for m in self.chat[:-1] if m["from"] != "system"]

        reply, source = self.brain.answer(text, lang, context, history)   # slow: outside the lock
        with self.lock:
            return self._answer(reply, "ask", source=source)

    def _answer(self, reply: str, route: str, source: str = "rules", kind: str = "chat",
                action: Optional[str] = None) -> dict:
        self._say("assistant", reply, kind=kind, source=source)
        return {"reply": reply, "route": route, "source": source, "action": action}

    def take_med(self, med_id: Optional[str] = None) -> dict:
        with self.lock:
            text = self._take_med(time.time(), med_id, self.engine.lang)
            self._say("assistant", text)
            return {"reply": text}

    def _take_med(self, now: float, med_id: Optional[str] = None, lang: str = "en") -> str:
        res = self.meds.take(now, med_id)
        if not res:
            return assistant.REPLIES["med_none"][lang]
        dose, med = res
        self._record([Event(now, "med_taken", f"{med.name} {med.dose} taken (due {_hhmm(dose.due_t)})", "user")])
        return (f"Bagus! {med.name} {med.dose} direkodkan diambil pada {_hhmm(now)}." if lang == "ms" else
                f"Great! I've recorded your {med.name} {med.dose} as taken at {_hhmm(now)}.")

    def _next_med_text(self, now: float, lang: str) -> str:
        nxt = self.meds.next_dose(now)
        if not nxt:
            return "Tiada ubat dijadualkan." if lang == "ms" else "You have no medicines scheduled."
        when = _hhmm(nxt["due_t"])
        return (f"Ubat seterusnya: {nxt['name']} {nxt['dose']} pada {when}. {nxt['instructions']}" if lang == "ms" else
                f"Your next medicine is {nxt['name']} {nxt['dose']} at {when}. {nxt['instructions']}")

    def submit_wellness(self, data: dict) -> dict:
        with self.lock:
            now = time.time()
            symptoms = [s for s in data.get("symptoms", []) if isinstance(s, str)][:20]
            note = str(data.get("note", ""))[:500]
            lang = data.get("lang") or self.engine.lang
            res = wellness.triage(data.get("mood"), data.get("pain"), data.get("sleep_h"), symptoms, note, lang)
            self.store.add_record("wellness", now, {"mood": data.get("mood"), "pain": data.get("pain"),
                                                    "sleep_h": data.get("sleep_h"), "symptoms": symptoms,
                                                    "note": note, "level": res["level"], "simulated": False})
            self._record([Event(now, "wellness_checkin", f"Daily check-in: {res['level'].replace('_', ' ')}"
                                + (f" — {'; '.join(res['reasons'])}" if res["reasons"] else ""), "user")])
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
            self._record([Event(time.time(), "pill_check",
                                f"Pill check: {res.get('medicine') or 'label not read'}"
                                + (f" (matches {res['matches']})" if res.get("matches") else ""), "assistant")])
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
                self._say("assistant", (f"Saya tidak dengar balasan, jadi saya telah memaklumkan {self.cfg.caregiver_name}. "
                                        "Bantuan sedang diminta." if self.engine.lang == "ms" else
                                        f"I didn't hear back, so I've alerted {self.cfg.caregiver_name}. Help is on the way."),
                          kind="alert")
            for action, dose, med in self.meds.tick(now):
                if action == "remind":
                    self._record([Event(now, "med_due", f"Reminder: {med.name} {med.dose}", "meds")])
                    self._say("assistant", assistant.MED_REMINDER[self.engine.lang].format(
                        name=med.name, dose=med.dose, instructions=med.instructions), kind="reminder")
                else:
                    grace = dose.grace_s if dose.grace_s is not None else self.cfg.med_grace_s
                    self._detect(Detection("missed_medication", now, [
                        f"{med.name} {med.dose} due at {_hhmm(dose.due_t)} was not confirmed within "
                        f"{grace / 60:.0f} min" if grace >= 120 else
                        f"{med.name} {med.dose} due at {_hhmm(dose.due_t)} was not confirmed within {grace:.0f}s"],
                        "The person may have taken it without telling me.", "meds"), now)
            if self.cfg.vitals_sim and now - self._vitals_t >= self.cfg.vitals_interval_s:
                self._vitals_t = now
                det = self.vitals.add(self.sim.next(), now, "simulated")
                self.version += 1
                if det:
                    self._detect(det, now)
            latest = self.vitals.latest()
            if latest and now - self._vitals_saved_t >= 300:
                self._vitals_saved_t = now
                self.store.add_record("vitals_daily", now, {**{k: latest.get(k) for k in ("hr", "spo2", "sys", "dia", "temp")},
                                                            "simulated": latest["source"] == "simulated"})
            self.routine.tick(now)

    # ---------- demo ----------
    def start_demo(self, name: str):
        if name not in demo.SCENARIOS:
            raise KeyError(name)
        self.stop_demo()
        with self.lock:
            self.detector.reset()
            self.routine.reset()
            self.demo_name = name
            self._demo_stop = threading.Event()   # fresh event per run: old threads keep their own
            setup = demo.SCENARIOS[name].get("setup", {})
            if "inactivity_s" in setup:
                self.routine.override_s = setup["inactivity_s"]
            if "dose_grace_s" in setup:
                self.meds.demo_dose(time.time(), setup["dose_grace_s"])
            if "vitals" in setup:
                self.sim.mode = setup["vitals"]
            self._record([Event(time.time(), "demo_started",
                                f"SIMULATED scenario started: {demo.SCENARIOS[name]['label']}", "demo")])
        threading.Thread(target=self._run_demo, args=(name, self._demo_stop), daemon=True).start()

    def stop_demo(self):
        self._demo_stop.set()
        with self.lock:
            if self.demo_name:
                self._end_demo()

    def _end_demo(self):
        self.demo_name = None
        self.detector.reset()
        self.routine.reset()
        self.routine.override_s = None
        self.sim.mode = "normal"
        self.meds.clear_demo()
        self.version += 1

    def _run_demo(self, name: str, stop: threading.Event):
        start = time.time()
        for offset, seg, angle, hip, motion, say in demo.frames(demo.SCENARIOS[name]["steps"]):
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
            r = self.routine
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
                "camera": {"mode": self.cfg.camera_mode, "running": self.camera.running, "error": self.camera.error,
                           "fps": round(self.camera.fps, 1),
                           "browser_connected": self.browser["connected"] > 0,
                           "browser_fps": self.browser["fps"] if now - self.browser["last_t"] < 3 else 0},
                "demo": {"running": self.demo_name,
                         "scenarios": {k: v["label"] for k, v in demo.SCENARIOS.items()}},
                "live": {"person": o.person, "posture": o.posture, "torso_angle": round(o.torso_angle),
                         "source": o.source, "motion": o.motion} if live_ok else None,
                "routine": {"still_s": round(now - r.still_since) if r.still_since else 0,
                            "threshold_s": round(r.threshold(now))},
                "meds": {"today": self.meds.today(now), "next": self.meds.next_dose(now),
                         "schedule": self.meds.schedule()},
                "vitals": {"latest": self.vitals.latest(), "history": self.vitals.history(90),
                           "simulated": self.cfg.vitals_sim, "mode": self.sim.mode},
                "ai": {"online": self.brain.online, "model": self.cfg.anthropic_model if self.brain.online else None},
                "notify": {"telegram": self.notifier.enabled},
                "profile": {"user_name": self.cfg.user_name, "caregiver_name": self.cfg.caregiver_name},
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
                "profile": {"user_name": self.cfg.user_name, "caregiver_name": self.cfg.caregiver_name},
                "adherence": adherence(self.store, now, days),
                "activity": self.routine.heatmap(now, days),
                "wellness": self.store.records("wellness", since=since),
                "vitals": self.store.records("vitals_daily", since=since),
                "incidents": [i for i in incidents if i["created_t"] >= since],
                "incident_counts": by_kind,
                "meds": self.meds.schedule(),
                "events": self.store.recent_events(200, since=since),
            }

    def _context_text(self, now: float) -> str:
        meds = ", ".join(f"{m.name} {m.dose} at {'/'.join(m.times)} ({m.purpose})" for m in self.meds.meds.values())
        nxt = self.meds.next_dose(now)
        v = self.vitals.latest()
        lines = [f"Medicines: {meds or 'none recorded'}"]
        if nxt:
            lines.append(f"Next dose: {nxt['name']} at {_hhmm(nxt['due_t'])} ({nxt['status']})")
        if v:
            lines.append(f"Latest readings{' (SIMULATED)' if v['source'] == 'simulated' else ''}: "
                         f"HR {v.get('hr')} bpm, SpO2 {v.get('spo2')}%, BP {v.get('sys')}/{v.get('dia')}, temp {v.get('temp')}°C")
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
                self.notifier.send(f"{icon} BAYMAX — {self.cfg.user_name}: {e.message}")
        for inc in self.engine.incidents.values():
            self.store.save_incident(inc)
        self.version += 1

    def _say(self, who: str, text: Optional[str], kind: str = "chat", source: Optional[str] = None):
        if not text:
            return
        self._msg_id += 1
        self.chat.append({"id": self._msg_id, "t": time.time(), "from": who, "text": text, "kind": kind,
                          "source": source})
        self.chat = self.chat[-100:]
        self.version += 1
