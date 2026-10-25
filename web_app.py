"""
FastAPI Live Monitoring Web Application for Advanced CCTV Analytics.
Provides MJPEG live stream, incident records, SOS notifications, and alarm controls.
"""

import time
import json
import logging
from pathlib import Path
from typing import Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import load_config, save_config, get_project_root
from core.analytics_engine import AnalyticsEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CCTV.Web")

PROJECT_ROOT = get_project_root()
config_data = load_config()

# Initialize global Analytics Engine
engine: AnalyticsEngine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    logger.info("Initializing CCTV Analytics Engine...")
    engine = AnalyticsEngine(config=config_data, project_root=PROJECT_ROOT)
    engine.start()
    yield
    logger.info("Shutting down CCTV Analytics Engine...")
    if engine:
        engine.stop()


app = FastAPI(title="Advanced CCTV Hazard Analytics", lifespan=lifespan)

# Mount static and snapshots directories
static_dir = PROJECT_ROOT / "web" / "static"
snapshots_dir = PROJECT_ROOT / "evidence" / "snapshots"
templates_dir = PROJECT_ROOT / "web" / "templates"

static_dir.mkdir(parents=True, exist_ok=True)
snapshots_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.mount("/snapshots", StaticFiles(directory=str(snapshots_dir)), name="snapshots")
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Renders the CCTV Command Center Web Dashboard."""
    return templates.TemplateResponse(
    request=request,
    name="index.html",
    context={"request": request}
)


def frame_generator():
    """Generates MJPEG multipart stream from connected hardware camera."""
    while True:
        if engine:
            jpeg_bytes = engine.wait_for_new_jpeg(timeout=0.035)
            if jpeg_bytes:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n")
            else:
                time.sleep(0.01)
        else:
            time.sleep(0.05)


@app.get("/video_feed")
async def video_feed():
    """Live MJPEG video feed endpoint."""
    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.get("/api/status")
async def get_status():
    """Returns real-time telemetry and detection metrics."""
    if not engine:
        return JSONResponse({"status": "initializing"}, status_code=503)
    return JSONResponse(engine.get_system_status())


@app.post("/api/silence_alarm")
async def silence_alarm():
    """Silences active alarm siren."""
    if engine:
        engine.alarm.silence()
    return JSONResponse({"status": "silenced"})


@app.post("/api/test_alarm")
async def test_alarm():
    """Triggers an audio siren test."""
    if engine:
        engine.alarm.trigger(hazard_type="SYSTEM TEST")
    return JSONResponse({"status": "triggered"})


@app.post("/api/test_sos")
async def test_sos():
    """Triggers a test SOS emergency alert with current frame snapshot."""
    if not engine:
        return JSONResponse({"error": "Engine not running"}, status_code=503)

    raw_frame = engine.latest_raw_frame
    if raw_frame is None:
        return JSONResponse({"error": "No camera frame available"}, status_code=400)

    loc = engine.locator.get_current_location()
    cam_name = engine.config.get("camera", {}).get("camera_name", f"Camera #{engine.camera.active_index}")

    snapshot_path = engine.dispatcher.save_evidence_snapshot(
        frame=raw_frame,
        hazard_type="DRILL TEST",
        confidence=0.99,
        camera_name=cam_name,
        location=loc
    )

    engine.dispatcher.dispatch_sos(
        hazard_type="DRILL TEST",
        confidence=0.99,
        camera_name=cam_name,
        location=loc,
        snapshot_path=snapshot_path
    )

    engine.alarm.trigger(hazard_type="DRILL TEST")
    return JSONResponse({"status": "sos_dispatched", "snapshot": snapshot_path.name})


@app.get("/api/incidents")
async def get_incidents():
    """Returns recent incidents log."""
    if not engine:
        return JSONResponse([])
    return JSONResponse(engine.dispatcher.get_recent_incidents())


@app.post("/api/settings")
async def update_settings(request: Request):
    """Updates runtime and saved settings."""
    data = await request.json()
    global config_data

    if "sos_phone_number" in data:
        config_data["sos_alert"]["sos_phone_number"] = data["sos_phone_number"]
    if "confidence_threshold" in data:
        conf = float(data["confidence_threshold"])
        config_data["detection"]["confidence_threshold"] = conf
        if engine:
            engine.detector.conf_threshold = conf
    if "consecutive_frames_required" in data:
        frames = int(data["consecutive_frames_required"])
        config_data["detection"]["consecutive_frames_required"] = frames
        if engine:
            engine.detector.consecutive_required = frames

    save_config(config_data)
    return JSONResponse({"status": "saved", "config": config_data})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=False)
