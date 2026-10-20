"""Plain data types shared by every stage of the pipeline."""
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

Source = Literal["camera", "demo", "user", "vitals", "meds", "routine"]
Posture = Literal["standing", "sitting", "lying", "upright", "upper body only", "unknown"]


@dataclass
class Observation:
    """One frame's worth of pose features. Produced by the camera OR by demo scenarios."""
    t: float                      # seconds (time.time())
    person: bool                  # was a person detected?
    torso_angle: float = 0.0      # 0 = upright, 90 = horizontal
    hip_y: float = 0.0            # normalised hip height in image (1 = bottom of frame)
    posture: Posture = "unknown"
    source: Source = "camera"
    full_body: bool = True        # shoulders AND hips actually visible (not guessed by the model)
    motion: Optional[float] = None  # mean landmark movement per frame (None = unknown)


DetectionKind = Literal["possible_fall", "inactivity", "vitals_alert", "missed_medication", "red_flag_symptom"]


@dataclass
class Detection:
    """Output of the FallDetector. Reasons explain *why*, so caregivers can judge."""
    kind: DetectionKind
    t: float
    reasons: list[str]
    uncertainty: str
    source: Source


@dataclass
class Event:
    """A timeline entry shown on the dashboard and stored in SQLite."""
    t: float
    kind: str                     # e.g. possible_fall, checkin_sent, user_ok, escalated ...
    message: str
    source: str = "system"
    incident_id: Optional[int] = None
    id: Optional[int] = None

    def dict(self):
        return asdict(self)


Severity = Literal["low", "medium", "critical"]
Status = Literal["open", "acknowledged", "resolved"]
UserResponse = Literal["pending", "ok", "help", "no_response", "not_required"]


@dataclass
class Incident:
    """A caregiver-facing alert with its lifecycle."""
    id: int
    kind: str
    created_t: float
    severity: Severity
    status: Status
    user_response: UserResponse
    reasons: list[str]
    uncertainty: str
    source: str
    checkin_deadline: Optional[float] = None
    escalated: bool = False
    escalation_reason: Optional[str] = None
    updated_t: float = 0.0
    notes: list[str] = field(default_factory=list)

    def dict(self):
        return asdict(self)
