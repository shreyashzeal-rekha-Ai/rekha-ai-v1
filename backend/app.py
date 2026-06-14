"""
backend/app.py
--------------
Expert CCTV — REST API Backend (v1)  [FastAPI Edition]

Serves:
  GET  /health                          — health check
  GET  /api/cameras                     — list cameras
  GET  /api/cameras/<id>                — get camera config
  POST /api/cameras/<id>/config         — save features + zones (from SettingsPage)
  GET  /api/cameras/<id>/stream         — MJPEG live stream
  GET  /api/cameras/<id>/snapshot       — single JPEG frame
  POST /api/cameras/<id>/zones          — save zones
  GET  /api/alerts                      — list alerts
  GET  /api/clips                       — list saved clips

NOTE: This backend does NOT run YOLO.
      YOLO runs in ai_engine/main.py (separate process).
      This backend only reads/writes cameras.json and MongoDB.
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta

# ── Strictly enforce Kolkata / IST timezone (UTC +05:30) ──────────────────────
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── resolve project root ─────────────────────────────────────────────
ROOT_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

# ── logging ──────────────────────────────────────────────────────────
LOG_DIR = os.path.join(ROOT_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, 'backend.log'), encoding='utf-8'),
    ]
)
logger = logging.getLogger("backend")

# ── FastAPI app ───────────────────────────────────────────────────────
app = FastAPI(
    title="Expert CCTV — REST API Backend",
    version="1.0.0",
    description="FastAPI backend for Expert CCTV surveillance system",
)

# Allow all origins for all routes (needed for React dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

FASTAPI_HOST = os.getenv("FASTAPI_HOST", os.getenv("FLASK_HOST", "0.0.0.0"))
FASTAPI_PORT = int(os.getenv("FASTAPI_PORT", os.getenv("FLASK_PORT", 5050)))

# ── Register route routers ────────────────────────────────────────────
from routes.cameras import cameras_router
from routes.alerts  import alerts_router
from routes.zones   import zones_router
from routes.clips   import clips_router
from routes.stream  import stream_router

app.include_router(cameras_router, prefix="/api")
app.include_router(alerts_router,  prefix="/api")
app.include_router(zones_router,   prefix="/api")
app.include_router(clips_router,   prefix="/api")
app.include_router(stream_router,  prefix="/api")

# ── Health endpoint ───────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":    "ok",
        "timestamp": datetime.now(IST).isoformat(),
    }


# ── Entry point ───────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("=" * 55)
    logger.info("  Expert CCTV — Backend API (FastAPI)")
    logger.info(f"  http://{FASTAPI_HOST}:{FASTAPI_PORT}")
    logger.info(f"  Docs: http://{FASTAPI_HOST}:{FASTAPI_PORT}/docs")
    logger.info("=" * 55)
    uvicorn.run(
        "app:app",
        host=FASTAPI_HOST,
        port=FASTAPI_PORT,
        reload=False,
        log_level="info",
    )
