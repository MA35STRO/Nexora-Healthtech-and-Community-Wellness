"""FastAPI entry point. Run from backend/:  uvicorn app.main:app --host 127.0.0.1 --port 8000

Serves the built dashboard (frontend/dist) on the same port, so one command runs everything.
"""

import asyncio
import base64
import binascii
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import daily_checkin
from .hub import Hub

hub = Hub()
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _ticker(stop: threading.Event):
    while not stop.wait(0.5):
        hub.tick()  # drives check-in timeouts, medication clock, simulated vitals


@asynccontextmanager
async def lifespan(_app):
    stop = threading.Event()
    threading.Thread(target=_ticker, args=(stop,), daemon=True).start()
    yield
    stop.set()
    hub.stop_demo()
    hub.inactivity.flush()


app = FastAPI(title="Kawan — AI Guardian for Independent Living", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    text: str


class ResolveIn(BaseModel):
    note: str = ""


class MedIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    dose: str = ""
    times: list[str] = Field(min_length=1, max_length=8)
    instructions: str = ""
    purpose: str = ""
    color: str = "#5b8def"


class TakeIn(BaseModel):
    med_id: Optional[str] = None


class VitalsIn(BaseModel):
    hr: Optional[float] = Field(None, ge=20, le=250)
    spo2: Optional[float] = Field(None, ge=50, le=100)
    sys: Optional[float] = Field(None, ge=50, le=260)
    dia: Optional[float] = Field(None, ge=30, le=160)
    temp: Optional[float] = Field(None, ge=30, le=45)
    source: str = "device"


class WellnessIn(BaseModel):
    mood: Optional[int] = Field(None, ge=1, le=5)
    pain: Optional[int] = Field(None, ge=0, le=10)
    sleep_h: Optional[float] = Field(None, ge=0, le=24)
    symptoms: list[str] = []
    note: str = ""
    lang: Optional[str] = None


class PillIn(BaseModel):
    image: str  # base64 JPEG (data: URL prefix allowed), sent only when the user taps "Check my medicine"


@app.get("/api/health")
def health():
    return {"ok": True, "ai_online": hub.brain.online}


class ProfileIn(BaseModel):
    user_name: Optional[str] = Field(None, max_length=60)
    caregiver_name: Optional[str] = Field(None, max_length=60)
    caregiver_phone: Optional[str] = Field(None, max_length=30)
    conditions: Optional[str] = Field(None, max_length=300)
    allergies: Optional[str] = Field(None, max_length=200)


@app.get("/api/profile")
def profile_get():
    return hub.profile()


@app.post("/api/profile")
def profile_set(body: ProfileIn):
    return hub.set_profile(body.model_dump(exclude_none=True))


@app.get("/api/state")
def state():
    return hub.snapshot()


@app.get("/api/insights")
def insights(days: int = 7):
    return hub.insights(max(1, min(days, 30)))


@app.post("/api/chat")
def chat(body: ChatIn):
    if not body.text.strip():
        raise HTTPException(400, "Empty message")
    return hub.user_message(body.text.strip()[:500])


@app.post("/api/incidents/{iid}/ack")
def ack(iid: int):
    if iid not in hub.engine.incidents:
        raise HTTPException(404, "Incident not found")
    hub.acknowledge(iid)
    return {"ok": True}


@app.post("/api/incidents/{iid}/resolve")
def resolve(iid: int, body: ResolveIn):
    if iid not in hub.engine.incidents:
        raise HTTPException(404, "Incident not found")
    hub.resolve(iid, body.note.strip()[:300])
    return {"ok": True}


# ---------- medication ----------
@app.get("/api/meds")
def meds_list():
    return {"schedule": hub.meds.schedule(), "today": hub.meds.today(time.time())}


@app.post("/api/meds")
def meds_add(body: MedIn):
    with hub.lock:
        med = hub.meds.add_med(body.model_dump())
        if not med.times:
            hub.meds.remove_med(med.id)
            raise HTTPException(400, "Times must look like HH:MM")
        hub.version += 1
    return {"ok": True, "id": med.id}


@app.delete("/api/meds/{med_id}")
def meds_remove(med_id: str):
    with hub.lock:
        if med_id not in hub.meds.meds:
            raise HTTPException(404, "Medicine not found")
        hub.meds.remove_med(med_id)
        hub.version += 1
    return {"ok": True}


@app.post("/api/meds/take")
def meds_take(body: TakeIn):
    return hub.take_med(body.med_id)


@app.post("/api/meds/snooze")
def meds_snooze():
    return hub.user_message("remind me later")


# ---------- vitals / wellness / pill check ----------
@app.post("/api/vitals")
def vitals_add(body: VitalsIn):
    """For real home devices (BP monitor, oximeter, smartwatch bridge) or a patient-data API."""
    data = body.model_dump()
    source = data.pop("source")[:20] or "device"
    if all(v is None for v in data.values()):
        raise HTTPException(400, "No readings supplied")
    return hub.add_vitals(data, source)


@app.get("/api/wellness/options")
def wellness_options():
    return {"symptoms": daily_checkin.SYMPTOM_CHOICES, "hotlines": daily_checkin.HOTLINES}


@app.post("/api/wellness")
def wellness_submit(body: WellnessIn):
    return hub.submit_wellness(body.model_dump())


@app.post("/api/pillcheck")
def pill_check(body: PillIn):
    raw = body.image.split(",", 1)[-1]
    if len(raw) > 2_000_000:
        raise HTTPException(413, "Image too large")
    try:
        base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "Image must be base64 JPEG")
    return hub.pill_check(raw)


# ---------- demo / reset ----------
@app.post("/api/demo/stop")
def demo_stop():
    hub.stop_demo()
    return {"ok": True}


@app.post("/api/demo/{name}")
def demo_start(name: str):
    try:
        hub.start_demo(name)
    except KeyError:
        raise HTTPException(404, "Unknown scenario")
    return {"ok": True}


@app.post("/api/reset")
def reset():
    hub.reset()
    return {"ok": True}


# ---------- websockets ----------
@app.websocket("/ws")
async def ws(socket: WebSocket):
    """Push a fresh snapshot whenever pipeline state changes (checked 5×/s)."""
    await socket.accept()
    sent = -1
    try:
        while True:
            if hub.version != sent:
                snap = hub.snapshot()
                sent = snap["version"]
                await socket.send_json(snap)
            await asyncio.sleep(0.2)
    except (WebSocketDisconnect, RuntimeError):
        pass


@app.websocket("/ws/perception")
async def ws_perception(socket: WebSocket):
    """Browser camera: receives {"lm": [[x, y, visibility] × 33] | null, "motion": float}. No images, ever."""
    await socket.accept()
    with hub.lock:
        hub.browser["connected"] += 1
    try:
        while True:
            msg = await socket.receive_json()
            lm = msg.get("lm") if isinstance(msg, dict) else None
            if lm is not None and not (isinstance(lm, list) and len(lm) <= 40):
                continue
            motion = msg.get("motion") if isinstance(msg, dict) else None
            motion = float(motion) if isinstance(motion, (int, float)) else None
            await socket.send_json(hub.ingest_points(lm, motion))
    except (WebSocketDisconnect, RuntimeError, ValueError, TypeError):
        pass
    finally:
        with hub.lock:
            hub.browser["connected"] -= 1
            hub.version += 1


# ---------- dashboard (built frontend) ----------
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
