"""All tunable thresholds live here so the safety rules are inspectable in one place."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # backend/


def _load_dotenv():
    """Tiny .env loader (backend/.env) so no extra dependency is needed. Real env vars win."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _s(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    # --- Fall detector (normalised image coords: y=0 top, y=1 bottom) ---
    window_s: float = _f("FALL_WINDOW_S", 1.5)            # how far back we look for a rapid drop
    min_drop: float = _f("FALL_MIN_DROP", 0.20)           # hip must drop this fraction of frame height...
    upright_angle: float = _f("FALL_UPRIGHT_ANGLE", 35)   # ...from an upright torso (deg from vertical)
    horizontal_angle: float = _f("FALL_HORIZONTAL_ANGLE", 60)  # ...to a near-horizontal torso
    still_s: float = _f("FALL_STILL_S", 2.0)              # and stay down this long before we flag it

    # --- Context engine ---
    checkin_timeout_s: float = _f("CHECKIN_TIMEOUT_S", 20)  # no reply within this → escalate

    # --- Routine / inactivity ---
    motion_threshold: float = _f("MOTION_THRESHOLD", 0.006)   # mean landmark movement per frame = "moving"
    inactivity_min_s: float = _f("INACTIVITY_MIN_S", 600)     # never flag stillness shorter than this
    inactivity_max_s: float = _f("INACTIVITY_MAX_S", 3600)    # learned threshold is capped here
    inactivity_k: float = _f("INACTIVITY_K", 1.5)             # × typical still period for this hour
    waking_start_h: float = _f("WAKING_START_H", 7)
    waking_end_h: float = _f("WAKING_END_H", 22)

    # --- Medication ---
    med_remind_again_s: float = _f("MED_REMIND_AGAIN_S", 600)  # repeat a reminder after 10 min
    med_grace_s: float = _f("MED_GRACE_S", 3600)               # dose counted as missed after 1 h
    med_snooze_s: float = _f("MED_SNOOZE_S", 600)

    # --- Vitals (simulated unless a device posts to /api/vitals) ---
    vitals_sim: bool = _s("VITALS_SIM", "1") == "1"
    vitals_interval_s: float = _f("VITALS_INTERVAL_S", 2)
    vitals_sustain_s: float = _f("VITALS_SUSTAIN_S", 20)       # abnormal must persist this long
    spo2_low: float = _f("SPO2_LOW", 92)
    hr_high: float = _f("HR_HIGH", 120)
    hr_low: float = _f("HR_LOW", 45)
    sys_crisis: float = _f("SYS_CRISIS", 180)
    dia_crisis: float = _f("DIA_CRISIS", 120)
    temp_fever: float = _f("TEMP_FEVER", 38.5)

    # --- AI (optional; everything works without a key) ---
    anthropic_api_key: str = _s("ANTHROPIC_API_KEY")
    anthropic_model: str = _s("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    llm_timeout_s: float = _f("LLM_TIMEOUT_S", 15)

    # --- Notifications (optional) ---
    telegram_token: str = _s("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = _s("TELEGRAM_CHAT_ID")

    # --- Profile ---
    user_name: str = _s("USER_NAME", "Mak Cik Aminah")
    caregiver_name: str = _s("CAREGIVER_NAME", "Farid (son)")
    seed_history: bool = _s("SEED_DEMO_HISTORY", "1") == "1"

    # --- Infra ---
    db_path: str = _s("BAYMAX_DB", str(ROOT / "baymax.db"))
    camera_mode: str = _s("CAMERA_MODE", "browser")   # browser (default) | server (OpenCV on this machine)
    camera_index: int = int(_f("CAMERA_INDEX", 0))
    model_path: str = _s("POSE_MODEL", str(ROOT / "models" / "pose_landmarker_lite.task"))


settings = Settings()
