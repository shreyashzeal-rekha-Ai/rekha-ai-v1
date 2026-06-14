import cv2
import numpy as np
import time
import logging
from typing import Optional

logger = logging.getLogger("feature_logic.tampering")

BASELINE_FRAMES         = 30
BASELINE_RESET_HOURS    = 1.0
SCENE_DIFF_THRESHOLD    = 0.15
SHIFT_CONFIRM_FRAMES    = 3
BRIGHTNESS_DROP_PCT     = 0.35
TAMPER_COOLDOWN_SECONDS = 3
MAX_ALERTS_BEFORE_RESET = 10
CLEAN_RESET_SECONDS     = 60


class TamperingDetector:

    def __init__(self, cam_id: str):
        self.cam_id = cam_id
        self._reset()

    def _reset(self):
        self._frame_count:          int                  = 0
        self._baseline_scene:       Optional[np.ndarray] = None
        self._baseline_bright:      Optional[float]      = None
        self._rolling_bright:       Optional[float]      = None
        self._collecting_bright:    list                 = []
        self._prev_gray:            Optional[np.ndarray] = None
        self._last_alert_time:      float                = 0.0
        self._last_tamper_time:     float                = 0.0
        self._baseline_set_time:    float                = 0.0
        self._shift_consecutive:    int                  = 0
        self._alert_count:          int                  = 0
        logger.debug(f"[{self.cam_id}] TamperingDetector reset.")

    def process(self, frame: np.ndarray, cam_state=None) -> list:
        if frame is None:
            return []

        gray       = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        self._frame_count += 1
        now = time.time()

        # ── Hourly hard reset ──────────────────────────────────────────
        if (self._baseline_set_time > 0 and
                (now - self._baseline_set_time) > BASELINE_RESET_HOURS * 3600):
            logger.info(f"[{self.cam_id}] Hourly baseline reset.")
            self._reset()
            return []

        # ── Phase 1: collect baseline ──────────────────────────────────
        if self._frame_count <= BASELINE_FRAMES:
            self._collecting_bright.append(brightness)
            if self._frame_count == BASELINE_FRAMES:
                small = cv2.resize(gray, (160, 120))
                self._baseline_scene    = small.astype(np.float32)
                self._baseline_bright   = float(np.mean(self._collecting_bright))
                self._rolling_bright    = self._baseline_bright
                self._baseline_set_time = now
                logger.info(f"[{self.cam_id}] Baseline set | brightness={self._baseline_bright:.1f}")
            self._prev_gray = gray.copy()
            return []

        # ── Rolling brightness EMA ─────────────────────────────────────
        if self._rolling_bright is not None:
            self._rolling_bright = 0.995 * self._rolling_bright + 0.005 * brightness

        # ── Phase 2: tamper checks ─────────────────────────────────────
        tamper_type = None
        details     = {}
        small = cv2.resize(gray, (160, 120)).astype(np.float32)

        # ── Check 1: COVER ─────────────────────────────────────────────
        if self._rolling_bright and self._rolling_bright > 10:
            bright_ratio = brightness / self._rolling_bright
            if bright_ratio < (1 - BRIGHTNESS_DROP_PCT):
                tamper_type = "cover"
                details = {
                    "brightness":      round(brightness, 1),
                    "baseline_bright": round(self._rolling_bright, 1),
                    "drop_pct":        round((1 - bright_ratio) * 100, 1),
                }
                logger.warning(f"[{self.cam_id}] COVER | brightness={brightness:.1f}")

        # ── Check 2: REPOSITIONED ──────────────────────────────────────
        if tamper_type is None and self._baseline_scene is not None:
            diff_norm = float(np.mean(np.abs(small - self._baseline_scene))) / 255.0

            if diff_norm > SCENE_DIFF_THRESHOLD:
                self._shift_consecutive += 1
                self._last_tamper_time = now

                if self._shift_consecutive >= SHIFT_CONFIRM_FRAMES:
                    tamper_type = "repositioned"
                    details = {
                        "scene_diff_pct": round(diff_norm * 100, 1),
                        "threshold_pct":  round(SCENE_DIFF_THRESHOLD * 100, 1),
                    }
                    # Reset so next alert needs re-confirmation
                    # DO NOT update baseline here — only alert 11 does that
                    self._shift_consecutive = 0

            else:
                self._shift_consecutive = 0

                # Clean reset: no tamper for 60s -> reset alert counter
                if (self._last_tamper_time > 0 and
                        (now - self._last_tamper_time) > CLEAN_RESET_SECONDS and
                        self._alert_count > 0):
                    logger.info(f"[{self.cam_id}] Camera normal 60s — alert counter reset.")
                    self._alert_count      = 0
                    self._last_tamper_time = 0.0

                # Slowly adapt baseline to gradual background changes
                cv2.accumulateWeighted(small, self._baseline_scene, 0.005)

        # ── Update prev frame ──────────────────────────────────────────
        self._prev_gray = gray.copy()

        if tamper_type is None:
            return []

        # ── DEBUG — remove after testing ──────────────────────────────
        logger.warning(f"[{self.cam_id}] DEBUG alert_count={self._alert_count} tamper={tamper_type} shift_consec={self._shift_consecutive}")

        # ── Cooldown ───────────────────────────────────────────────────
        if (now - self._last_alert_time) < TAMPER_COOLDOWN_SECONDS:
            return []

        self._last_alert_time = now
        self._alert_count += 1

        # ── Alert 11: update baseline, go silent ──────────────────────
        if self._alert_count > MAX_ALERTS_BEFORE_RESET:
            alert_message = "New camera angle captured. Baseline updated. Alerts stopped."
            severity      = "LOW"
            logger.info(f"[{self.cam_id}] Alert 11 — baseline updated to new position.")

            self._baseline_scene    = small.copy()
            self._baseline_bright   = brightness
            self._rolling_bright    = brightness
            self._baseline_set_time = now
            self._alert_count       = 0
            self._shift_consecutive = 0
            self._last_tamper_time  = 0.0

        # ── Alerts 1-10 ───────────────────────────────────────────────
        else:
            base_msg      = _tamper_message(tamper_type)
            alert_message = f"{base_msg} (Alert {self._alert_count}/{MAX_ALERTS_BEFORE_RESET})"
            severity      = "HIGH"
            logger.warning(f"[{self.cam_id}] Tamper alert {self._alert_count}/{MAX_ALERTS_BEFORE_RESET} | {tamper_type}")

        return [{
            "feature":     "tampering",
            "class":       "tampering",
            "confidence":  1.0,
            "bbox":        [0, 0, 0, 0],
            "cam_id":      self.cam_id,
            "tamper_type": tamper_type,
            "message":     alert_message,
            "severity":    severity,
            **details,
        }]


def _tamper_message(tamper_type: str) -> str:
    messages = {
        "cover":        "Camera lens appears to be covered or blocked",
        "repositioned": "Camera has been physically moved or repositioned",
    }
    return messages.get(tamper_type, "Camera tampering detected")