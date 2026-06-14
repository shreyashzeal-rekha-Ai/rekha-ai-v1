"""
feature_logic/criminal_face.py
-------------------------------
Criminal / Watchlist Face Recognition.

Logic:
  - Uses the `face_recognition` library (dlib-based)
  - Loads criminal_encodings.pkl  (copied from old project's encodings.pkl)
  - Processes every 2nd frame at 0.25x scale for speed
  - Matches detected faces against the watchlist
  - "Unknown" faces are ignored — only KNOWN names trigger alerts
  - Alert cooldown per identity so the same face doesn't spam

Watchlist setup:
  1. Add criminal photos to:
       ai_engine/models/criminal_faces/<PersonName>/photo1.jpg
  2. Run:  python ai_engine/encode_criminals.py
  3. Restart AI engine

"""

import os
import logging
import pickle
import time

import cv2
import numpy as np

logger = logging.getLogger("feature_logic.criminal_face")

ALERT_COOLDOWN_S = 30       # seconds between re-alerts for the same identity
TOLERANCE        = 0.45     # lower = stricter match (0.45 is strict)
SCALE            = 0.25     # resize factor for faster processing
PROCESS_EVERY_N  = 2        # run face_recognition every N frames

# Per-camera frame counter  {cam_id: int}
_frame_counters: dict = {}
# Per-camera last face locations (reuse between frames we skip)
_last_faces:     dict = {}   # {cam_id: [(top,right,bottom,left,name), ...]}

# Encodings loaded once
_known_encodings = None
_known_names     = None

def _load_encodings():
    global _known_encodings, _known_names
    if _known_encodings is not None:
        return True   # already loaded

    enc_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models", "criminal_encodings.pkl"
    )
    if not os.path.exists(enc_path):
        logger.error(
            f"[CriminalFace] criminal_encodings.pkl not found at {enc_path}. "
            "Run encode_criminals.py to generate it."
        )
        return False

    try:
        with open(enc_path, "rb") as f:
            data = pickle.load(f)
        _known_encodings = data["encodings"]
        _known_names     = data["names"]
        logger.info(
            f"[CriminalFace] Loaded {len(_known_names)} watchlist face(s): "
            f"{list(set(_known_names))}"
        )
        return True
    except Exception as e:
        logger.error(f"[CriminalFace] Failed to load encodings: {e}")
        return False


class CriminalFaceDetector:
    """
    Matches faces in the frame against the criminal/watchlist encodings.
    Fires an alert when a known name is recognised.
    """

    @staticmethod
    def process(frame, cam_id: str, cam_state) -> list:
        alerts = []
        if frame is None:
            return alerts

        # Lazy-load face_recognition (optional dep — graceful failure)
        try:
            import face_recognition as fr
        except ImportError:
            logger.error(
                "[CriminalFace] 'face_recognition' package not installed. "
                "Run: pip install face-recognition"
            )
            return alerts

        if not _load_encodings():
            return alerts

        if cam_id not in _frame_counters:
            _frame_counters[cam_id] = 0
            _last_faces[cam_id]     = []

        _frame_counters[cam_id] += 1
        skip = (_frame_counters[cam_id] % PROCESS_EVERY_N != 0)

        if not skip:
            # Downscale for speed
            small = cv2.resize(frame, (0, 0), fx=SCALE, fy=SCALE)
            rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            try:
                locations  = fr.face_locations(rgb)
                encodings  = fr.face_encodings(rgb, locations)
            except Exception as e:
                logger.debug(f"[{cam_id}] face_recognition error: {e}")
                return alerts

            faces_this_frame = []
            for enc, (top, right, bottom, left) in zip(encodings, locations):
                name = "Unknown"
                if len(_known_encodings) > 0:
                    matches    = fr.compare_faces(_known_encodings, enc, tolerance=TOLERANCE)
                    distances  = fr.face_distance(_known_encodings, enc)
                    best_idx   = int(np.argmin(distances))
                    if matches[best_idx]:
                        name = _known_names[best_idx]

                # Scale coords back to full frame
                scale_inv = int(1 / SCALE)
                faces_this_frame.append((
                    top    * scale_inv,
                    right  * scale_inv,
                    bottom * scale_inv,
                    left   * scale_inv,
                    name
                ))

                if name != "Unknown":
                    cooldown_key = f"criminal_face_{cam_id}_{name}"
                    if not cam_state.is_cooldown_active(cooldown_key, ALERT_COOLDOWN_S):
                        cam_state.mark_alerted(cooldown_key)
                        h, w = frame.shape[:2]
                        alerts.append({
                            "feature":    "criminal_face",
                            "class":      name,
                            "confidence": round(1.0 - float(distances[best_idx]), 3),
                            "bbox":       [
                                left   * scale_inv,
                                top    * scale_inv,
                                right  * scale_inv,
                                bottom * scale_inv,
                            ],
                            "cam_id":     cam_id,
                            "message":    f"🚨 WATCHLIST MATCH: {name} detected on camera {cam_id}",
                        })
                        logger.warning(
                            f"[{cam_id}] 🚨 CRIMINAL FACE: {name} "
                            f"distance={distances[best_idx]:.3f}"
                        )

            _last_faces[cam_id] = faces_this_frame

        return alerts


def get_last_faces(cam_id: str) -> list:
    """
    Returns the last detected face boxes for annotation.
    Each item: (top, right, bottom, left, name)
    """
    return _last_faces.get(cam_id, [])
