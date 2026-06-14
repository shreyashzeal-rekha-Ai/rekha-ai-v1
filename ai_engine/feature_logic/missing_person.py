"""
feature_logic/missing_person.py
--------------------------------
Missing Person Detector.

Logic:
  A "monitored zone" (type="missing_person") must have at least one person
  present at all times.
  If the zone is empty for > timeout_seconds → fire alert.
  Alert repeats every 60s while zone stays empty.

  Use case: Guard post, cashier station, receptionist desk.

How the timer works:
  • When the AI engine sees a person inside the zone  → timer resets to NOW.
  • When the zone is empty for the first time          → timer starts from NOW.
  • When the zone has been empty >= timeout_seconds   → alert fires.
  • Each time the zone polygon is redrawn/saved        → timer resets so the
    new countdown starts fresh from that moment.
"""

import time
import logging
import hashlib
import json
from feature_logic.intrusion import _point_in_polygon

logger = logging.getLogger("feature_logic.missing_person")

PERSON_CLASSES = {"person", "Person", "PERSON"}

# Only count a detection as "zone occupied" if confidence is high enough.
# This prevents background objects (chairs, shadows, mannequins) from
# keeping the zone "occupied" and blocking the missing-person alert.
MIN_OCCUPANCY_CONF = 0.35   # tuned: PersonTracker already needs 2 frames to emit a track

# Per-camera + per-zone last-seen tracker
# Key: "{cam_id}::{zone_id}"  →  last timestamp a person was seen inside
_zone_last_seen: dict = {}

# Track the polygon hash per zone to detect user redraws and auto-reset timer.
# Key: "{cam_id}::{zone_id}"  →  sha1 hex of the polygon points JSON
_zone_polygon_hash: dict = {}


def _polygon_hash(polygon: list) -> str:
    """Return a short hash of the polygon coordinates to detect changes."""
    return hashlib.sha1(json.dumps(polygon, sort_keys=True).encode()).hexdigest()[:12]


def reset_zone(cam_id: str, zone_id: str):
    """
    Call this when a zone is redrawn / config is saved so the countdown
    starts fresh from NOW instead of continuing from the old timer.
    """
    key = f"{cam_id}::{zone_id}"
    _zone_last_seen.pop(key, None)
    _zone_polygon_hash.pop(key, None)
    logger.info(f"[missing_person] Timer reset for {key} (zone redrawn / config saved)")


def reset_camera(cam_id: str):
    """Remove all timer state for a camera (called on camera delete/restart)."""
    keys = [k for k in list(_zone_last_seen.keys()) if k.startswith(f"{cam_id}::")]
    for k in keys:
        _zone_last_seen.pop(k, None)
        _zone_polygon_hash.pop(k, None)
    logger.info(f"[missing_person] All timers cleared for camera {cam_id}")


class MissingPersonDetector:
    """
    Alerts when a critical-role zone (guard post etc.) has been
    empty for longer than timeout_seconds.
    """

    @staticmethod
    def process(
        result,
        cam_id: str,
        cam_state,
        zones: list,
        timeout_seconds: int = 180,  # 3 minutes default
        target_count: int = 1        # Number of expected persons
    ) -> list:
        """
        Args:
            result:           YOLO track result (may be None on no-motion frames)
            cam_id:           camera identifier
            cam_state:        CameraState for cooldown management
            zones:            list of zone dicts; uses type=="missing_person"
            timeout_seconds:  seconds of emptiness before first alert fires

        Returns:
            List of alert dicts for each zone that is empty too long.
        """
        monitored_zones = [z for z in zones if z.get("type") == "missing_person"]
        if not monitored_zones:
            return []

        now    = time.time()
        alerts = []

        # ── Collect high-confidence center-points for currently visible persons ──
        # Only persons with conf >= MIN_OCCUPANCY_CONF count as "zone occupied".
        # Low-confidence detections (chairs, shadows, reflections) are ignored.
        person_points = []
        if result is not None and result.boxes is not None:
            boxes = result.boxes
            names = result.names or {}
            for i in range(len(boxes)):
                cls_name = names.get(int(boxes.cls[i].item()), "unknown")
                if cls_name not in PERSON_CLASSES:
                    continue
                # Confidence gate — skip borderline detections
                conf = float(boxes.conf[i].item()) if boxes.conf is not None and len(boxes.conf) > i else 1.0
                if conf < MIN_OCCUPANCY_CONF:
                    logger.debug(f"[{cam_id}] Skipping low-conf person ({conf:.2f}) for occupancy check")
                    continue
                xyxy   = boxes.xyxy[i].tolist()
                cx = (xyxy[0] + xyxy[2]) / 2
                cy = (xyxy[1] + xyxy[3]) / 2
                person_points.append((cx, cy))

        src = "no-motion" if result is None else "GPU"
        logger.debug(f"[{cam_id}] missing_person check via {src}: {len(person_points)} confirmed person(s) in zone-check")

        # ── Pre-compute frame scale (canvas 1280×720 → inference dims) ─
        # result.orig_shape is only available when result is not None.
        # When result is None (no-motion frame) the polygon coords are already
        # in 1280×720 canvas space so we use a 1:1 scale.
        if result is not None and hasattr(result, 'orig_shape') and result.orig_shape is not None:
            h, w = result.orig_shape
            _sx, _sy = w / 1280.0, h / 720.0
        else:
            _sx, _sy = 1.0, 1.0

        for zone in monitored_zones:
            zone_id   = zone["id"]
            state_key = f"{cam_id}::{zone_id}"   # per-camera key (fixes multi-cam bug)
            polygon   = zone.get("polygon", [])
            if len(polygon) < 3:
                continue

            # ── Auto-reset timer when the polygon is redrawn ──────────
            # If the user saves a new zone shape, we detect the change via
            # a hash of the coordinates and reset the empty-timer to NOW.
            current_hash = _polygon_hash(polygon)
            if _zone_polygon_hash.get(state_key) != current_hash:
                _zone_polygon_hash[state_key] = current_hash
                _zone_last_seen[state_key]    = now   # start fresh countdown
                logger.info(
                    f"[{cam_id}] Zone '{zone.get('name')}' polygon changed — "
                    f"timer reset. Countdown: {timeout_seconds}s"
                )
                continue  # give 1 frame grace before starting evaluation

            # Scale polygon to match inference dimensions
            scaled_poly = [[int(pt[0]*_sx), int(pt[1]*_sy)] for pt in polygon]

            # Count how many people are inside this zone right now
            people_present = sum(
                1 for cx, cy in person_points
                if _point_in_polygon(cx, cy, scaled_poly)
            )

            if people_present >= target_count:
                # Target count met or exceeded → reset timer
                _zone_last_seen[state_key] = now
                logger.debug(
                    f"[{cam_id}] Zone '{zone.get('name')}' occupied ({people_present}/{target_count}) — timer reset ✅"
                )
            else:
                # Zone is missing people (less than target count)

                last_seen = _zone_last_seen.get(state_key)
                if last_seen is None:
                    _zone_last_seen[state_key] = now
                    continue

                empty_seconds = now - last_seen
                logger.debug(
                    f"[{cam_id}] Zone '{zone.get('name')}' missing persons ({people_present}/{target_count}) "
                    f"for {empty_seconds:.1f}s / {timeout_seconds}s"
                )

                if empty_seconds >= timeout_seconds:
                    # Repeat alert every 60s (once per minute) while zone stays empty
                    cooldown_key    = f"missing_person_{state_key}"
                    repeat_cooldown = 60
                    if not cam_state.is_cooldown_active(cooldown_key, repeat_cooldown):
                        cam_state.mark_alerted(cooldown_key)
                        mins = int(empty_seconds) // 60
                        secs = int(empty_seconds) % 60
                        duration_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                        alerts.append({
                            "feature":       "missing_person",
                            "class":         "missing_person",
                            "confidence":    1.0,
                            "bbox":          [0, 0, 0, 0],
                            "cam_id":        cam_id,
                            "zone_name":     zone.get("name", "Unknown Zone"),
                            "empty_seconds": round(empty_seconds, 0),
                            "message":       (
                                f"Zone '{zone.get('name','?')}' missing expected persons! "
                                f"Only {people_present}/{target_count} found for {duration_str}"
                            ),
                        })
                        logger.warning(
                            f"[{cam_id}] 🚨 Missing person | "
                            f"zone='{zone.get('name')}' missing expected persons for {empty_seconds:.0f}s"
                        )

        return alerts
