"""
feature_logic/weapon_detection.py
----------------------------------
Weapon Detection — uses the custom weapon.pt YOLO model from old project.

Detects: gun, knife, pistol, firearm, revolver, handgun
Logic:
  - Runs on every frame where motion is detected
  - Requires min_confidence (0.60) + min_box_area (1500px²)
  - Consecutive detection filter (3 frames) prevents false positives
  - Alert fires with cooldown so it doesn't spam
"""

import os
import logging
import time
from ultralytics import YOLO
import torch

logger = logging.getLogger("feature_logic.weapon_detection")

# Actual class names from weapon.pt (run: python -c "from ultralytics import YOLO; m=YOLO('models/weapon.pt'); print(m.names)")
VALID_WEAPONS    = {"guns", "knife", "gun", "pistol", "firearm", "revolver", "handgun"}  # all variants
MIN_CONF         = 0.50          # lowered from 0.60 — weapon.pt may score lower
MIN_BOX_AREA     = 800           # lowered from 1500 — webcam at distance = smaller boxes
CONSECUTIVE_REQ  = 2            # 2 back-to-back frames (was 3)
ALERT_COOLDOWN_S = 20

# Per-camera consecutive frame counters  {cam_id: count}
_consec: dict = {}

# Weapon model is loaded lazily once
_model  = None
_device = None

def _get_model():
    global _model, _device
    if _model is None:
        _device = "cuda:0" if torch.cuda.is_available() else "cpu"
        model_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "models", "weapon.pt"
        )
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"weapon.pt not found at {model_path}")
        _model = YOLO(model_path)
        _model.to(_device)
        logger.info(f"[WeaponDetector] Loaded weapon.pt on {_device}")
    return _model, _device


class WeaponDetector:
    """
    Runs weapon.pt on every frame.  Returns alert dicts when a weapon is
    confirmed (consecutive detection filter applied).
    """

    @staticmethod
    def process(frame, cam_id: str, cam_state) -> list:
        alerts = []
        if frame is None:
            return alerts

        try:
            model, device = _get_model()
        except FileNotFoundError as e:
            logger.error(str(e))
            return alerts

        if cam_id not in _consec:
            _consec[cam_id] = 0

        try:
            results = model.predict(
                source=frame,
                conf=MIN_CONF,
                verbose=False,
                device=device,
            )
        except Exception as e:
            logger.error(f"[{cam_id}] Weapon inference error: {e}")
            return alerts

        detected     = False
        best_conf    = 0.0
        best_label   = ""
        best_bbox    = [0, 0, 0, 0]

        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].int().tolist()
                cls   = int(box.cls[0].item())
                conf  = float(box.conf[0].item())
                label = model.names[cls].lower()

                # Area + class filter
                area = (x2 - x1) * (y2 - y1)
                if area < MIN_BOX_AREA:
                    continue
                if label not in VALID_WEAPONS:
                    continue
                if conf < MIN_CONF:
                    continue

                if conf > best_conf:
                    detected   = True
                    best_conf  = conf
                    best_label = label
                    best_bbox  = [x1, y1, x2, y2]

        if detected:
            _consec[cam_id] += 1
            logger.debug(
                f"[{cam_id}] Weapon candidate '{best_label}' "
                f"conf={best_conf:.2f} consec={_consec[cam_id]}"
            )
            if _consec[cam_id] >= CONSECUTIVE_REQ:
                cooldown_key = f"weapon_{cam_id}"
                if not cam_state.is_cooldown_active(cooldown_key, ALERT_COOLDOWN_S):
                    cam_state.mark_alerted(cooldown_key)
                    alerts.append({
                        "feature":    "weapon_detection",
                        "class":      best_label,
                        "confidence": round(best_conf, 3),
                        "bbox":       best_bbox,
                        "cam_id":     cam_id,
                        "message":    (
                            f"⚠️ WEAPON DETECTED: {best_label.upper()} "
                            f"({best_conf*100:.1f}% confidence)"
                        ),
                    })
                    logger.warning(
                        f"[{cam_id}] 🔫 WEAPON ALERT: {best_label} conf={best_conf:.2f}"
                    )
        else:
            _consec[cam_id] = 0   # reset on clean frame

        return alerts
