"""
feature_logic/crowd.py
-----------------------
Crowd Monitoring Detector (v1 — ACTIVE).

Logic:
  Count all persons detected in frame (or optionally within a crowd zone polygon).
  If count > max_count threshold → fire alert.
  Uses a camera-level cooldown to avoid alert spam every frame.
"""

import logging
from ultralytics.engine.results import Results
from feature_logic.intrusion import _point_in_polygon

logger = logging.getLogger("feature_logic.crowd")

PERSON_CLASSES = {"person", "Person", "PERSON"}

CROWD_COOLDOWN_SECONDS = 30  # minimum seconds between crowd alerts


class CrowdDetector:
    """
    Alerts when the number of people in frame (or zone) exceeds a threshold.
    """

    @staticmethod
    def process(
        result: Results,
        cam_id: str,
        cam_state,         # CameraState instance
        max_count: int = 2,
        zones: list = None  # optional crowd zone polygons
    ) -> list[dict]:
        """
        Args:
            result:    YOLO track result
            cam_id:    camera identifier
            cam_state: CameraState for cooldown management
            max_count: person count threshold
            zones:     optional list of zone dicts with type=="crowd"
                       If None or empty, counts whole frame.

        Returns:
            List with one crowd alert dict (or empty if under threshold).
        """
        if result is None or result.boxes is None:
            return []

        boxes = result.boxes
        names = result.names

        crowd_zones = [z for z in (zones or []) if z.get("type") == "crowd"]

        # --- Count persons ---
        if crowd_zones:
            # Count only within each crowd zone
            all_detections = []
            for zone in crowd_zones:
                polygon = zone.get("polygon", [])
                if len(polygon) < 3:
                    continue
                h, w = result.orig_shape
                sx, sy = w / 1280.0, h / 720.0
                scaled_poly = [[int(pt[0]*sx), int(pt[1]*sy)] for pt in polygon]
                
                count = 0
                persons_in_zone = []
                for i in range(len(boxes)):
                    cls_id   = int(boxes.cls[i].item())
                    cls_name = names.get(cls_id, "unknown")
                    if cls_name not in PERSON_CLASSES:
                        continue
                    xyxy = boxes.xyxy[i].tolist()
                    foot_x = (xyxy[0] + xyxy[2]) / 2
                    foot_y = xyxy[3]
                    if _point_in_polygon(foot_x, foot_y, scaled_poly):
                        count += 1
                        persons_in_zone.append([int(v) for v in xyxy])

                cam_state.last_crowd_count = count

                if count > max_count:
                    if not cam_state.is_cooldown_active("crowd", CROWD_COOLDOWN_SECONDS):
                        cam_state.mark_alerted("crowd")
                        all_detections.append({
                            "feature":    "crowd",
                            "class":      "crowd",
                            "confidence": 1.0,
                            "bbox":       persons_in_zone[0] if persons_in_zone else [0, 0, 0, 0],
                            "cam_id":     cam_id,
                            "count":      count,
                            "threshold":  max_count,
                            "zone_name":  zone.get("name", "Zone"),
                        })
                        logger.info(
                            f"[{cam_id}] 👥 Crowd alert | zone='{zone.get('name')}' "
                            f"count={count} threshold={max_count}"
                        )
            return all_detections

        else:
            # Count entire frame
            count = sum(
                1 for i in range(len(boxes))
                if names.get(int(boxes.cls[i].item()), "unknown") in PERSON_CLASSES
            )
            cam_state.last_crowd_count = count

            if count > max_count:
                if not cam_state.is_cooldown_active("crowd", CROWD_COOLDOWN_SECONDS):
                    cam_state.mark_alerted("crowd")
                    logger.info(
                        f"[{cam_id}] 👥 Crowd alert | count={count} threshold={max_count}"
                    )
                    return [{
                        "feature":    "crowd",
                        "class":      "crowd",
                        "confidence": 1.0,
                        "bbox":       [0, 0, 0, 0],
                        "cam_id":     cam_id,
                        "count":      count,
                        "threshold":  max_count,
                        "zone_name":  "Full Frame",
                    }]

        return []
