"""
alert_engine.py
---------------
Receives structured detections from feature_logic processors.
Decides whether to fire an alert (cooldown check),
saves snapshot, writes to JSON file (always works - no MongoDB needed),
and optionally to MongoDB if available.

Fixes:
  - Tampering bypasses alert_engine cooldown (manages its own internally)
  - Severity from detection dict is respected (tampering sends LOW for alert 11)
  - message field from detection is passed through to alert_doc
"""

import os
import json
import time
import queue
import logging
import threading
import cv2
from datetime import datetime, timezone, timedelta

# ── Strictly enforce Kolkata / IST timezone (UTC +05:30) ──────────────────────
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
from dotenv import load_dotenv
from whatsapp_notifier import WhatsAppNotifier

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger("alert_engine")

MONGO_URI       = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB        = os.getenv("MONGO_DB", "expert_cctv")
ALERT_COOLDOWN  = int(os.getenv("ALERT_COOLDOWN_SECONDS", 30))
SNAPSHOT_DIR    = os.path.join(os.path.dirname(__file__), '..', 'clips')
SAVE_SNAPSHOTS  = os.getenv("SAVE_SNAPSHOTS", "True").strip().lower() in ("true", "1", "yes")
ROOT_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALERTS_JSON     = os.path.join(ROOT_DIR, 'alerts.json')
MAX_JSON_ALERTS = 200

# Features that manage their own cooldown internally — skip alert_engine cooldown
SELF_COOLDOWN_FEATURES = {"tampering", "loitering", "vehicle_detection"}


class AlertEngine:
    def __init__(self, event_queue: queue.Queue):
        self.event_queue = event_queue
        self._lock       = threading.Lock()
        self._last_alert: dict[str, float] = {}

        self.alerts_col = None
        try:
            from pymongo import MongoClient
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            client.server_info()
            self.alerts_col = client[MONGO_DB]["alerts"]
            logger.info(f"[AlertEngine] ✅ MongoDB connected: {MONGO_URI}")
        except Exception as e:
            logger.warning(f"[AlertEngine] ⚠️  MongoDB not available ({e}). Using JSON fallback.")

        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        if not os.path.exists(ALERTS_JSON):
            with open(ALERTS_JSON, 'w') as f:
                json.dump([], f)

        self.whatsapp = WhatsAppNotifier()
        self.whatsapp.start()
        logger.info("[AlertEngine] WhatsApp notifier started.")

    # ── Main entry point ───────────────────────────────────────────────
    def process(self, detections: list[dict], frame, cam_id: str, feature: str):
        if not detections:
            return

        # Intrusion / no-go zone: only fire if person is inside a zone
        if feature in ("intrusion", "no_go_zone"):
            detections = [d for d in detections if d.get("in_zone", False)]
            if not detections:
                return

        # ── Cooldown — skipped for features that manage their own ──────
        if feature not in SELF_COOLDOWN_FEATURES:
            cooldown_key = f"{cam_id}:{feature}"
            with self._lock:
                now     = time.time()
                elapsed = now - self._last_alert.get(cooldown_key, 0)
                if elapsed < ALERT_COOLDOWN:
                    return
                self._last_alert[cooldown_key] = now

        ts          = datetime.now(IST)
        snapshot_fn = self._save_snapshot(frame, cam_id, feature, ts)

        # ── Pull message + severity from detection if provided ─────────
        # Tampering sends its own message ("Alert 3/10") and severity ("LOW" for alert 11)
        first_detection = detections[0] if detections else {}
        detection_message  = first_detection.get("message")
        detection_severity = first_detection.get("severity")
        detection_tamper_type = first_detection.get("tamper_type")

        alert_doc = {
            "_id":           f"{cam_id}_{feature}_{int(ts.timestamp())}",
            "cam_id":        cam_id,
            "feature":       feature,
            "timestamp":     ts.isoformat(),
            "detections":    detections,
            "snapshot_path": snapshot_fn,
            # Use severity from detection if provided, else default
            "severity":      detection_severity or self._severity(feature),
            # Pass through message from detection (tampering alert count message)
            "message":       detection_message or "",
        }

        # Add tamper_type to alert_doc if present
        if detection_tamper_type:
            alert_doc["tamper_type"] = detection_tamper_type

        # ── 1. Write to JSON ───────────────────────────────────────────
        self._write_json(alert_doc)

        # ── 2. Write to MongoDB ────────────────────────────────────────
        if self.alerts_col is not None:
            try:
                doc_copy = dict(alert_doc)
                doc_copy.pop("_id", None)
                result = self.alerts_col.insert_one(doc_copy)
                alert_doc["_id"] = str(result.inserted_id)
            except Exception as e:
                logger.error(f"[AlertEngine] MongoDB write failed: {e}")

        # ── 3. Push to WebSocket queue ─────────────────────────────────
        try:
            self.event_queue.put_nowait(alert_doc)
        except queue.Full:
            pass

        # ── 4. WhatsApp notification ───────────────────────────────────
        self.whatsapp.send(alert_doc, frame)

        # ── 5. Push to backend real-time notification endpoint ─────────
        def post_to_backend(doc):
            try:
                import requests
                requests.post("http://localhost:5050/api/alerts/notify", json=doc, timeout=1.5)
            except Exception as ex:
                logger.debug(f"[AlertEngine] Backend real-time notify failed: {ex}")

        threading.Thread(target=post_to_backend, args=(alert_doc,), daemon=True).start()

        logger.info(
            f"🚨 ALERT | cam={cam_id} | feature={feature} "
            f"| severity={alert_doc['severity']} | detections={len(detections)}"
            + (f" | {detection_message}" if detection_message else "")
        )

    def _write_json(self, alert_doc: dict):
        try:
            with self._lock:
                try:
                    with open(ALERTS_JSON, 'r') as f:
                        alerts = json.load(f)
                except Exception:
                    alerts = []
                alerts.insert(0, alert_doc)
                alerts = alerts[:MAX_JSON_ALERTS]
                with open(ALERTS_JSON, 'w') as f:
                    json.dump(alerts, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"[AlertEngine] JSON write failed: {e}")

    def _save_snapshot(self, frame, cam_id: str, feature: str, ts: datetime) -> str:
        """
        Save the alert snapshot.

        `frame` is the ANNOTATED 1280×720 frame (zone outlines, Person #ID boxes,
        fire/weapon bounding boxes, HUD timestamp) passed in from main.py.
        Saved at JPEG quality 95 so the labels are clearly readable.
        """
        if not SAVE_SNAPSHOTS:
            return ""
        fn = f"{cam_id}_{feature}_{ts.strftime('%Y%m%d_%H%M%S')}.jpg"
        fp = os.path.join(SNAPSHOT_DIR, fn)
        try:
            cv2.imwrite(fp, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        except Exception as e:
            logger.error(f"[AlertEngine] Snapshot save failed: {e}")
            return ""
        logger.debug(f"[AlertEngine] Snapshot saved: {fn}")
        return fn

    @staticmethod
    def _severity(feature: str) -> str:
        return {
            "fire_smoke":           "CRITICAL",
            "no_go_zone":           "CRITICAL",
            "perimeter":            "HIGH",
            "intrusion":            "HIGH",
            "missing_person":       "HIGH",
            "tampering":            "HIGH",
            "loitering":            "MEDIUM",
            "crowd":                "MEDIUM",
            "personal_monitoring":  "MEDIUM",
            "footfall":             "LOW",
            "animal_detection":     "HIGH",   # Phase 2 (per-animal severity in detection dict overrides this)
            "vehicle_detection":    "MEDIUM", # Phase 3
        }.get(feature, "MEDIUM")