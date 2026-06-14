"""
ai_engine/whatsapp_notifier.py
-------------------------------
Sends WhatsApp alerts when the AI engine detects a security event.
Uses Meta's WhatsApp Business Cloud API (Graph API v18.0).

Features:
  - Rich formatted message with full alert details
  - Snapshot photo attached to every alert (uploaded via media API)
  - Per-camera per-feature cooldown so the guard is NOT spammed
    (CRITICAL: 60s cooldown, HIGH: 120s, MEDIUM: 300s, LOW: never sent)
  - Runs in a background daemon thread — never blocks the inference loop

Setup (Meta WhatsApp Business Cloud API):
  1. Go to https://developers.facebook.com and create an App (Business type)
  2. Add "WhatsApp" product to your app
  3. In WhatsApp > API Setup, copy:
       - Access Token         → WHATSAPP_ACCESS_TOKEN  in .env
       - Phone Number ID      → WHATSAPP_PHONE_NUMBER_ID in .env
  4. Add recipient number    → WHATSAPP_TO_NUMBER in .env  (include country code, e.g. 919876543210)
  5. Verify the recipient number in the Meta test console before going live.

Usage:
  from whatsapp_notifier import WhatsAppNotifier
  notifier = WhatsAppNotifier()
  notifier.send(alert_doc, frame)
"""

import io
import os
import cv2
import time
import queue
import logging
import threading
import requests
from datetime import datetime, timezone, timedelta

# ── Strictly enforce Kolkata / IST timezone (UTC +05:30) ──────────────────────
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

logger = logging.getLogger("whatsapp_notifier")

# ── Credentials (loaded from .env) ───────────────────────────────────────────
WHATSAPP_ACCESS_TOKEN    = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_TO_NUMBER       = os.getenv("WHATSAPP_TO_NUMBER", "")   # e.g. 919876543210

# Meta Graph API base
_GRAPH_BASE = "https://graph.facebook.com/v18.0"

# ── Cooldown per severity (seconds between same cam+feature WhatsApp messages) ─
WA_COOLDOWN = {
    "CRITICAL": 60,    # fire, weapon, criminal — alert every 1 min max
    "HIGH":     120,   # intrusion, perimeter   — alert every 2 min max
    "MEDIUM":   300,   # crowd (default)        — alert every 5 min max
    "LOW":      None,  # footfall               — never send to WhatsApp
}

# Loitering repeats every dwell_seconds — WhatsApp must not block those repeats.
LOITERING_WA_COOLDOWN = int(os.getenv("LOITERING_WA_COOLDOWN_SECONDS", "55"))

# ── Feature display names and emojis ─────────────────────────────────────────
FEATURE_LABELS = {
    "fire_smoke":          ("🔥", "Fire / Smoke"),
    "no_go_zone":          ("⛔", "No-Go Zone Breach"),
    "weapon_detection":    ("🔫", "Weapon Detected"),
    "criminal_face":       ("🚨", "Criminal Face Identified"),
    "intrusion":           ("👤", "Intrusion Detected"),
    "perimeter":           ("🚧", "Perimeter Breach"),
    "missing_person":      ("❓", "Person Missing from Zone"),
    "tampering":           ("📷", "Camera Tampering"),
    "loitering":           ("🚶", "Loitering Detected"),
    "crowd":               ("👥", "Crowd Alert"),
    "personal_monitoring": ("📍", "Personnel Monitoring"),
    "footfall":            ("📊", "Footfall Count"),
}


def _build_message(alert_doc: dict) -> str:
    """Build a rich Markdown-formatted message from an alert dict.
    Format is identical to the original Telegram alerts.
    WhatsApp supports *bold*, _italic_, and `monospace` natively.
    """
    feature  = alert_doc.get("feature", "unknown")
    cam_id   = alert_doc.get("cam_id",  "unknown")
    severity = alert_doc.get("severity","MEDIUM")
    ts_iso   = alert_doc.get("timestamp", datetime.now(IST).isoformat())
    dets     = alert_doc.get("detections", [])

    emoji, label = FEATURE_LABELS.get(feature, ("⚠️", feature.replace("_", " ").title()))

    # Format timestamp to IST-friendly
    try:
        dt_utc = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        dt_ist = dt_utc.astimezone(IST)
        ts_str = dt_ist.strftime("%d %b %Y  %H:%M:%S IST")
    except Exception:
        ts_str = ts_iso

    # Severity badge
    sev_badge = {
        "CRITICAL": "🔴 CRITICAL",
        "HIGH":     "🟠 HIGH",
        "MEDIUM":   "🟡 MEDIUM",
        "LOW":      "🔵 LOW",
    }.get(severity, f"⚪ {severity}")

    lines = [
        f"{emoji} *{label}*",
        f"",
        f"📍 *Camera:*  {cam_id}",
        f"🕐 *Time:*    {ts_str}",
        f"⚡ *Severity:* {sev_badge}",
    ]

    # Add detection-specific details
    if dets:
        det = dets[0]

        if feature == "criminal_face":
            name = det.get("class") or det.get("name", "Unknown")
            conf = det.get("confidence", 0)
            lines.append(f"👤 *Identity:* {name} ({conf*100:.0f}% match)")

        elif feature == "weapon_detection":
            wtype = (det.get("class") or "Weapon").upper()
            conf  = det.get("confidence", 0)
            lines.append(f"🔫 *Type:* {wtype} ({conf*100:.0f}% confidence)")

        elif feature == "perimeter":
            lines.append(f"🚧 *{det.get('alert_type','person').capitalize()} crossed boundary*")
            if det.get("class"):
                lines.append(f"   Class: {det['class']}")

        elif feature == "loitering":
            dwell = det.get("dwell_seconds") or det.get("loiter_seconds")
            count = det.get("count")
            ids   = det.get("loitering_ids") or det.get("all_ids_in_zone") or []
            if count is not None:
                lines.append(f"👥 *People in zone:* {count}")
            if ids:
                id_str = ", ".join(f"#{i}" for i in ids)
                lines.append(f"🆔 *Person IDs:* {id_str}")
            if dwell:
                lines.append(f"⏱ *Dwell time:* {dwell}s")

        elif feature == "missing_person":
            zone = det.get("zone_name", "")
            empty = det.get("empty_seconds", "")
            if zone:
                lines.append(f"📌 *Zone:* {zone} — empty {empty}s")

        elif feature == "crowd":
            count = det.get("count", len(dets))
            lines.append(f"👥 *People count:* {count}")

        elif feature == "fire_smoke":
            classes = list({d.get("class","fire") for d in dets})
            lines.append(f"🔥 *Detected:* {', '.join(classes)}")

        conf_general = det.get("confidence")
        if conf_general and feature not in ("criminal_face", "weapon_detection"):
            lines.append(f"🎯 *Confidence:* {conf_general*100:.1f}%")

    lines.append(f"")
    lines.append(f"_Trinetra AI · AI Surveillance Intelligence_")

    return "\n".join(lines)


class WhatsAppNotifier(threading.Thread):
    """
    Background thread that processes WhatsApp notification jobs.
    Non-blocking: the inference loop just enqueues jobs and continues.

    Uses Meta WhatsApp Business Cloud API:
      - Text  → POST /messages  (type=text)
      - Image → POST /media (upload) → POST /messages (type=image with media_id)
    """

    def __init__(self):
        super().__init__(daemon=True, name="whatsapp-notifier")
        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._last_sent: dict    = {}   # {cam_id:feature -> timestamp}
        self._lock = threading.Lock()
        self._running = True

        # Detect unfilled placeholder values
        _placeholders = {
            "YOUR_PERMANENT_ACCESS_TOKEN_HERE",
            "YOUR_PHONE_NUMBER_ID_HERE",
            "YOUR_RECIPIENT_NUMBER_HERE",
            "",
        }
        _all_set = (
            WHATSAPP_ACCESS_TOKEN    not in _placeholders and
            WHATSAPP_PHONE_NUMBER_ID not in _placeholders and
            WHATSAPP_TO_NUMBER       not in _placeholders
        )

        if _all_set:
            self._enabled = True
            self._headers = {
                "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
                "Content-Type":  "application/json",
            }
            logger.info("[WhatsAppNotifier] ✅ Credentials loaded. Notifier enabled.")
        else:
            self._enabled = False
            logger.error(
                "[WhatsAppNotifier] ❌ CREDENTIALS NOT SET. "
                "WhatsApp alerts are DISABLED. "
                "Open .env and fill in:\n"
                "  WHATSAPP_ACCESS_TOKEN      ← from developers.facebook.com → Your App → WhatsApp → API Setup\n"
                "  WHATSAPP_PHONE_NUMBER_ID   ← same page\n"
                "  WHATSAPP_TO_NUMBER         ← recipient number with country code (e.g. 919876543210)"
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def send(self, alert_doc: dict, frame=None):
        """
        Non-blocking enqueue. Called from AlertEngine after an alert fires.
        Applies cooldown check before enqueuing.
        """
        feature  = alert_doc.get("feature", "")
        cam_id   = alert_doc.get("cam_id", "")
        severity = alert_doc.get("severity", "MEDIUM")

        # ── GATE 1: credentials not set ──────────────────────────────
        if not self._enabled:
            logger.warning(
                f"[WhatsAppNotifier] ⛔ GATE 1 — Credentials not set or still placeholder. "
                f"Alert for {feature} on {cam_id} NOT sent. Fill .env values."
            )
            return

        # ── GATE 2: LOW severity never sends ─────────────────────────
        cooldown = LOITERING_WA_COOLDOWN if feature == "loitering" else WA_COOLDOWN.get(severity)
        if cooldown is None:
            logger.debug(
                f"[WhatsAppNotifier] ⛔ GATE 2 — Severity=LOW, skipping WhatsApp for {feature} on {cam_id}."
            )
            return

        # ── GATE 3: per-cam cooldown window ──────────────────────────
        key = f"{cam_id}:{feature}"
        with self._lock:
            last    = self._last_sent.get(key, 0)
            elapsed = time.time() - last
            if elapsed < cooldown:
                logger.debug(
                    f"[WhatsAppNotifier] ⛔ GATE 3 — Cooldown active for {feature} on {cam_id}. "
                    f"Wait {cooldown - elapsed:.0f}s more (cooldown={cooldown}s)."
                )
                return
            self._last_sent[key] = time.time()

        logger.info(
            f"[WhatsAppNotifier] ✅ Queueing alert: {feature} on {cam_id} (severity={severity})"
        )

        # Encode frame snapshot
        frame_bytes = None
        if frame is not None:
            try:
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ok:
                    frame_bytes = buf.tobytes()
            except Exception:
                pass

        job = {"alert_doc": alert_doc, "frame_bytes": frame_bytes}
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            logger.warning("[WhatsAppNotifier] Queue full — skipping notification.")


    def run(self):
        """Worker: processes jobs from the queue in a dedicated thread."""
        logger.info("[WhatsAppNotifier] Worker thread started.")
        while self._running:
            try:
                job = self._queue.get(timeout=1)
                self._dispatch(job)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[WhatsAppNotifier] Dispatch error: {e}")

    def stop(self):
        self._running = False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _dispatch(self, job: dict):
        """Send text message + optional image to WhatsApp."""
        alert_doc   = job["alert_doc"]
        frame_bytes = job["frame_bytes"]
        msg         = _build_message(alert_doc)

        # 1. Send text message
        self._send_text(msg)

        # 2. Upload image and send as media message (if snapshot available)
        if frame_bytes:
            media_id = self._upload_media(frame_bytes)
            if media_id:
                caption = (
                    f"📸 Snapshot — {alert_doc.get('cam_id')} "
                    f"/ {alert_doc.get('feature')}"
                )
                self._send_image(media_id, caption)

        logger.info(
            f"[WhatsAppNotifier] ✅ Sent: {alert_doc.get('feature')} "
            f"on {alert_doc.get('cam_id')}"
        )

    def _send_text(self, body: str) -> bool:
        """Send a plain text WhatsApp message."""
        url     = f"{_GRAPH_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to":   WHATSAPP_TO_NUMBER,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": body,
            },
        }
        try:
            resp = requests.post(url, json=payload, headers=self._headers, timeout=10)
            if resp.status_code == 200:
                return True
            else:
                logger.error(
                    f"[WhatsAppNotifier] Text send failed "
                    f"({resp.status_code}): {resp.text}"
                )
                return False
        except Exception as e:
            logger.error(f"[WhatsAppNotifier] Text send error: {e}")
            return False

    def _upload_media(self, frame_bytes: bytes) -> str | None:
        """
        Upload JPEG bytes to the WhatsApp media endpoint.
        Returns the media_id string on success, or None on failure.
        """
        url = f"{_GRAPH_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/media"
        # Use multipart upload — no JSON content-type here
        upload_headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
        files = {
            "file": ("snapshot.jpg", io.BytesIO(frame_bytes), "image/jpeg"),
        }
        data = {"messaging_product": "whatsapp"}
        try:
            resp = requests.post(
                url, headers=upload_headers, files=files, data=data, timeout=30
            )
            if resp.status_code == 200:
                media_id = resp.json().get("id")
                return media_id
            else:
                logger.error(
                    f"[WhatsAppNotifier] Media upload failed "
                    f"({resp.status_code}): {resp.text}"
                )
                return None
        except Exception as e:
            logger.error(f"[WhatsAppNotifier] Media upload error: {e}")
            return None

    def _send_image(self, media_id: str, caption: str) -> bool:
        """Send an already-uploaded image using its media_id."""
        url     = f"{_GRAPH_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to":   WHATSAPP_TO_NUMBER,
            "type": "image",
            "image": {
                "id":      media_id,
                "caption": caption,
            },
        }
        try:
            resp = requests.post(url, json=payload, headers=self._headers, timeout=10)
            if resp.status_code == 200:
                return True
            else:
                logger.error(
                    f"[WhatsAppNotifier] Image send failed "
                    f"({resp.status_code}): {resp.text}"
                )
                return False
        except Exception as e:
            logger.error(f"[WhatsAppNotifier] Image send error: {e}")
            return False
