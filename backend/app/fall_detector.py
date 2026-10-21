"""Temporal possible-fall detector.

A single horizontal pose is NOT a fall (people lie on sofas). We require a sequence:
  1. Upright torso, then a rapid hip drop (>= min_drop of frame height within window_s)
  2. Torso ends near-horizontal (or the person drops out of view)
  3. They stay down for still_s seconds
Only then do we emit "possible_fall" — with human-readable reasons.
"""

from collections import deque
from typing import Optional

from .config import Settings
from .config import settings as default_settings
from .data_types import Detection, Observation


class FallDetector:
    def __init__(self, cfg: Settings = default_settings):
        self.cfg = cfg
        self.history: deque[Observation] = deque()
        self.candidate: Optional[dict] = None  # set when a rapid drop is seen
        self.cooldown_until = 0.0

    def reset(self):
        self.history.clear()
        self.candidate = None
        self.cooldown_until = 0.0

    @staticmethod
    def usable(o: Observation) -> bool:
        return o.person and o.full_body  # never reason on landmarks the model had to guess

    def update(self, obs: Observation) -> Optional[Detection]:
        self._remember(obs)

        if self.candidate is None:
            if obs.t >= self.cooldown_until:
                self.candidate = self._find_rapid_drop(obs)
            return None

        return self._confirm_or_cancel(obs)

    # --- step 1: rapid descent from upright ---
    def _find_rapid_drop(self, now: Observation) -> Optional[dict]:
        if not self.usable(now):
            return None
        upright = [o for o in self.history if self.usable(o) and o.torso_angle <= self.cfg.upright_angle]
        if not upright:
            return None
        start = min(upright, key=lambda o: o.hip_y)  # highest hip position in the window
        drop = now.hip_y - start.hip_y
        if drop < self.cfg.min_drop or now.t <= start.t:
            return None
        return {
            "t": now.t,
            "drop": drop,
            "duration": now.t - start.t,
            "start_angle": start.torso_angle,
        }

    # --- steps 2+3: still down (or out of view) for still_s? ---
    def _confirm_or_cancel(self, obs: Observation) -> Optional[Detection]:
        c = self.candidate
        if self.usable(obs):
            c["low_hip"] = max(c.get("low_hip", 0), obs.hip_y)
            c["max_angle"] = max(c.get("max_angle", 0), obs.torso_angle)
        else:
            c["lost"] = True

        # "Got up" = upright again AND hips rose well above their lowest point
        got_up = (
            (
                self.usable(obs)
                and obs.torso_angle <= self.cfg.upright_angle
                and obs.hip_y < c["low_hip"] - self.cfg.min_drop / 2
            )
            if "low_hip" in c
            else False
        )
        if got_up:
            self.candidate = None  # they recovered on their own — no alert
            return None

        if obs.t - c["t"] < self.cfg.still_s:
            return None

        horizontal = c.get("max_angle", 0) >= self.cfg.horizontal_angle
        lost = c.get("lost", False) and not self.usable(obs)
        if not (horizontal or lost):
            self.candidate = None  # dropped but ended e.g. sitting/crouching: not flagged
            return None

        reasons = [
            f"Hip position dropped {c['drop'] * 100:.0f}% of frame height in {c['duration']:.1f}s "
            f"from an upright posture"
        ]
        if horizontal:
            reasons.append(f"Torso became near-horizontal ({c['max_angle']:.0f}° from vertical)")
        if lost:
            reasons.append("Person left the camera view (or became only partly visible) right after the drop")
        reasons.append(f"No recovery to standing within {self.cfg.still_s:.0f}s")
        uncertainty = (
            "Camera-based estimate only. Could also be lying down quickly, "
            "bending out of view, or tracking error. User check-in required."
        )

        self.candidate = None
        self.cooldown_until = obs.t + 10  # avoid duplicate detections for the same fall
        return Detection("possible_fall", obs.t, reasons, uncertainty, obs.source)

    def _remember(self, obs: Observation):
        self.history.append(obs)
        while self.history and obs.t - self.history[0].t > self.cfg.window_s:
            self.history.popleft()
