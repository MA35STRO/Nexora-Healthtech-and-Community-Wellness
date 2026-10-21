"""Context engine: a deterministic, testable state machine for safety decisions.

Rules (all explicit — no LLM involved):
  R1 possible_fall / inactivity / vitals_alert → open incident (medium), send check-in, start timeout
  R2 user replies "ok"                → severity low, caregiver informed (no escalation)
  R3 user replies "help" (any time)   → severity critical, ESCALATE
  R4 no reply before deadline         → severity critical, ESCALATE ("no response")
  R5 unclear reply                    → ask again; timeout keeps running
  R6 caregiver acknowledges/resolves  → status changes; resolved incidents close
  R7 new detection of the same kind while one is open → merged into it (no duplicate alerts)
  R8 red-flag symptom reported        → severity critical, ESCALATE immediately (no check-in)
  R9 missed medication                → low-severity caregiver notice (no check-in, no timeout)
  R10 "I'm okay" answers every pending check-in at once

Time is passed in (`now`) rather than read from the clock, so tests can fast-forward.
"""

from typing import Optional

from . import conversation
from .config import Settings
from .config import settings as default_settings
from .data_types import Detection, Event, Incident

# kind → (starting severity, needs a check-in with the user?)
PROFILE = {
    "possible_fall": ("medium", True),
    "inactivity": ("medium", True),
    "vitals_alert": ("medium", True),
    "missed_medication": ("low", False),
    "red_flag_symptom": ("critical", False),
}
LABEL = {
    "possible_fall": "Possible fall",
    "inactivity": "Unusual inactivity",
    "vitals_alert": "Vital signs alert",
    "missed_medication": "Missed medication",
    "red_flag_symptom": "Emergency warning sign reported",
}


class SafetyEngine:
    def __init__(self, cfg: Settings = default_settings, next_id: int = 1):
        self.cfg = cfg
        self.incidents: dict[int, Incident] = {}
        self.next_id = next_id
        self.lang: conversation.Lang = "en"
        self.pending_prompt: Optional[str] = None  # what the assistant is currently asking the user

    # ---------- derived state ----------
    @property
    def active(self) -> Optional[Incident]:
        """The most urgent open incident: escalated > waiting for the user > notices; then newest."""
        open_ = [i for i in self.incidents.values() if i.status != "resolved"]
        rank = lambda i: (2 if i.escalated else 1 if i.user_response == "pending" else 0, i.created_t)
        return max(open_, key=rank) if open_ else None

    @property
    def state(self) -> str:
        a = self.active
        if a is None:
            return "monitoring"
        if a.escalated:
            return "escalated"
        if a.user_response == "pending":
            return "check_in"
        return "attention"  # e.g. user said OK; caregiver hasn't closed it yet

    def pending_deadline(self) -> Optional[float]:
        ds = [p.checkin_deadline for p in self._pending() if p.checkin_deadline]
        return min(ds) if ds else None

    # ---------- inputs ----------
    def on_detection(self, det: Detection, now: float) -> list[Event]:
        label = LABEL[det.kind]
        same = self._open(det.kind)
        if same is not None:  # R7
            same.notes.append(f"{label} detected again during this incident")
            same.updated_t = now
            return [
                Event(
                    now,
                    det.kind,
                    f"{label} detected again (merged into incident #{same.id})",
                    det.source,
                    same.id,
                )
            ]

        severity, check_in = PROFILE[det.kind]
        inc = self._new_incident(det.kind, now, severity, det.reasons, det.uncertainty, det.source)
        events = [Event(now, det.kind, f"{label}: " + "; ".join(det.reasons), det.source, inc.id)]
        if det.kind == "red_flag_symptom":  # R8
            self._escalate(
                inc, now, "User reported emergency warning signs: " + "; ".join(det.reasons), "help", events
            )
        elif not check_in:  # R9
            inc.user_response = "not_required"
            events.append(
                Event(now, "caregiver_notice", f"Caregiver informed: {label.lower()}", "system", inc.id)
            )
        else:  # R1
            inc.checkin_deadline = now + self.cfg.checkin_timeout_s
            self.pending_prompt = conversation.CHECKIN[det.kind][self.lang]
            events.append(Event(now, "checkin_sent", self.pending_prompt, "assistant", inc.id))
        return events

    def report_red_flag(self, reasons: list[str], text: str, now: float) -> list[Event]:
        return self.on_detection(
            Detection(
                "red_flag_symptom", now, reasons, f'Reported by the user: "{text}". Not a diagnosis.', "user"
            ),
            now,
        )

    def on_user_message(self, text: str, now: float) -> tuple[str, list[Event]]:
        self.lang = conversation.wants_lang(text, self.lang)
        intent = conversation.classify(text)
        a = self.active
        events = [Event(now, "user_message", text, "user", a.id if a else None)]

        if intent == "help":  # R3 — honoured even with no active incident
            if a is None or a.status == "resolved":
                a = self._new_incident(
                    "help_request",
                    now,
                    "critical",
                    [f'User asked for help: "{text}"'],
                    "Reported directly by the user.",
                    "user",
                )
            self._escalate(a, now, f'User requested help: "{text}"', "help", events)
            return self._reply("help"), events

        pending = self._pending()
        if not pending:
            return self._reply("idle"), events

        if intent == "ok":  # R2 + R10
            for p in pending:
                p.user_response = "ok"
                p.severity = "low"
                p.checkin_deadline = None
                p.updated_t = now
                events.append(
                    Event(
                        now,
                        "user_ok",
                        "User reported they are okay. Caregiver informed (low severity).",
                        "system",
                        p.id,
                    )
                )
            self.pending_prompt = None
            return self._reply("ok"), events

        events.append(
            Event(
                now,
                "checkin_repeat",
                "Reply unclear; asked again. Timeout still running.",
                "assistant",
                pending[0].id,
            )
        )  # R5
        return self._reply("unclear"), events

    def tick(self, now: float) -> list[Event]:
        events: list[Event] = []
        for p in self._pending():  # R4
            if p.checkin_deadline and now >= p.checkin_deadline:
                self._escalate(
                    p,
                    now,
                    f"No response to check-in within {self.cfg.checkin_timeout_s:.0f}s",
                    "no_response",
                    events,
                )
        return events

    def acknowledge(self, incident_id: int, now: float) -> list[Event]:
        inc = self.incidents[incident_id]
        if inc.status != "open":
            return []
        inc.status = "acknowledged"
        inc.updated_t = now
        return [Event(now, "acknowledged", "Caregiver acknowledged the alert", "caregiver", inc.id)]

    def resolve(self, incident_id: int, now: float, note: str = "") -> list[Event]:
        inc = self.incidents[incident_id]
        if inc.status == "resolved":
            return []
        inc.status = "resolved"
        inc.checkin_deadline = None
        inc.updated_t = now
        if note:
            inc.notes.append(note)
        self._refresh_prompt()
        return [
            Event(
                now,
                "resolved",
                "Caregiver resolved the alert" + (f": {note}" if note else ""),
                "caregiver",
                inc.id,
            )
        ]

    # ---------- helpers ----------
    def _open(self, kind: str) -> Optional[Incident]:
        return next((i for i in self.incidents.values() if i.status != "resolved" and i.kind == kind), None)

    def _pending(self) -> list[Incident]:
        return sorted(
            (i for i in self.incidents.values() if i.status != "resolved" and i.user_response == "pending"),
            key=lambda i: i.created_t,
        )

    def _new_incident(self, kind, now, severity, reasons, uncertainty, source) -> Incident:
        inc = Incident(
            self.next_id,
            kind,
            now,
            severity,
            "open",
            "pending",
            list(reasons),
            uncertainty,
            source,
            updated_t=now,
        )
        self.incidents[inc.id] = inc
        self.next_id += 1
        return inc

    def _escalate(self, inc: Incident, now: float, reason: str, response: str, events: list[Event]):
        inc.user_response = response
        inc.severity = "critical"
        inc.escalated = True
        inc.escalation_reason = reason
        inc.checkin_deadline = None
        inc.updated_t = now
        if inc.status == "resolved":
            inc.status = "open"
        self._refresh_prompt()
        events.append(Event(now, "escalated", f"ESCALATED to caregiver: {reason}", "system", inc.id))

    def _refresh_prompt(self):
        """Keep asking about any check-in that is still waiting; otherwise stop asking."""
        pending = self._pending()
        self.pending_prompt = conversation.CHECKIN[pending[0].kind][self.lang] if pending else None

    def _reply(self, key: str) -> str:
        return conversation.REPLIES[key][self.lang]
