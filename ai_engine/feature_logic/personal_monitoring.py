"""
feature_logic/personal_monitoring.py
--------------------------------------
Personal Monitoring Detector (v1 — ACTIVE, Zone-Based).

V1 = Zone-based presence monitoring (no face recognition needed).
V2 = Face-recognition watchlist matching (requires face model).

Logic (V1):
  A "personal_monitoring" zone tracks whether someone is present in their
  designated spot (receptionist desk, guard post, sales counter).
  If zone is empty for > timeout_seconds → absence alert.
  If zone has someone after being empty → "returned" info log.

  This is subtly different from missing_person:
    - missing_person: a CRITICAL role must always be present
    - personal_monitoring: tracks presence for operational insights
      (e.g. salesperson away from counter for 5 min during business hours)

  Both use the same zone-empty logic — personal_monitoring has lower severity.
"""

import time
import logging
from ultralytics.engine.results import Results
from feature_logic.intrusion import _point_in_polygon

logger = logging.getLogger("feature_logic.personal_monitoring")

PERSON_CLASSES = {"person", "Person", "PERSON"}

_zone_last_seen: dict[str, float] = {}   # {zone_id: timestamp}
_zone_was_empty: dict[str, bool]  = {}   # {zone_id: True if alert already fired}


class PersonalMonitoringDetector:
    """
    Tracks zone-based presence of personnel and alerts on prolonged absence.
    """

    @staticmethod
    def process(
        result: Results,
        cam_id: str,
        cam_state,
        zones: list,
        timeout_seconds: int = 300
    ) -> list[dict]:
        """
        Args:
            result:           YOLO track result
            cam_id:           camera identifier
            cam_state:        CameraState for cooldown
            zones:            list of zone dicts; uses type=="personal_monitoring"
            timeout_seconds:  absence duration before alert

        Returns:
            List of alert dicts.
        """
        if result is None:
            return []

        pm_zones = [z for z in zones if z.get("type") == "personal_monitoring"]
        if not pm_zones:
            return []

        boxes  = result.boxes
        names  = result.names if boxes is not None else {}
        now    = time.time()
        alerts = []

        # Build foot-points of all visible persons
        person_feet = []
        if boxes is not None:
            for i in range(len(boxes)):
                cls_name = names.get(int(boxes.cls[i].item()), "unknown")
                if cls_name in PERSON_CLASSES:
                    xyxy   = boxes.xyxy[i].tolist()
                    foot_x = (xyxy[0] + xyxy[2]) / 2
                    foot_y = xyxy[3]
                    person_feet.append((foot_x, foot_y))

        for zone in pm_zones:
            zone_id = zone["id"]
            polygon = zone.get("polygon", [])
            if len(polygon) < 3:
                continue

            # Scale polygon to match inference dimensions
            h, w = result.orig_shape
            sx, sy = w / 1280.0, h / 720.0
            scaled_poly = [[int(pt[0]*sx), int(pt[1]*sy)] for pt in polygon]

            someone_present = any(
                _point_in_polygon(fx, fy, scaled_poly)
                for fx, fy in person_feet
            )

            if someone_present:
                _zone_last_seen[zone_id] = now
                if _zone_was_empty.get(zone_id):
                    logger.info(
                        f"[{cam_id}] ✅ Personnel returned to zone "
                        f"'{zone.get('name')}'"
                    )
                _zone_was_empty[zone_id] = False
            else:
                last_seen = _zone_last_seen.get(zone_id)
                if last_seen is None:
                    _zone_last_seen[zone_id] = now
                    continue

                empty_seconds = now - last_seen
                if empty_seconds >= timeout_seconds:
                    if not _zone_was_empty.get(zone_id, False):
                        _zone_was_empty[zone_id] = True
                        cooldown_key = f"personal_monitoring_{zone_id}"
                        if not cam_state.is_cooldown_active(cooldown_key, timeout_seconds):
                            cam_state.mark_alerted(cooldown_key)
                            alerts.append({
                                "feature":       "personal_monitoring",
                                "class":         "absent",
                                "confidence":    1.0,
                                "bbox":          [0, 0, 0, 0],
                                "cam_id":        cam_id,
                                "zone_name":     zone.get("name", "Monitored Zone"),
                                "empty_seconds": round(empty_seconds, 0),
                            })
                            logger.warning(
                                f"[{cam_id}] 👤 Personnel absent | "
                                f"zone='{zone.get('name')}' "
                                f"since={empty_seconds:.0f}s"
                            )
        return alerts
