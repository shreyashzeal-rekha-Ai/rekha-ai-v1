"""
feature_logic/no_go_zone.py
----------------------------
No-Go Zone Detector (v1 — ACTIVE).

Logic:
  Any person detected with foot-point inside a no-go polygon → instant alert.
  No time threshold — ANY presence is an immediate violation.

  Difference from intrusion.py:
    - intrusion.py = restricted zone (usually with time-delay or access policy)
    - no_go_zone   = absolute prohibition (strong room, transformer yard, terrace)
    - Severity = CRITICAL vs HIGH

Uses the shared _point_in_polygon function from intrusion.py.
"""

import logging
import cv2
import numpy as np
from ultralytics.engine.results import Results
from feature_logic.intrusion import _point_in_polygon

logger = logging.getLogger("feature_logic.no_go_zone")

PERSON_CLASSES = {"person", "Person", "PERSON"}


class NoGoZoneDetector:
    """
    Instant alert on any person detected inside a no-go zone polygon.
    """
    _in_zone: dict = {}  # { f"{cam_id}_{zone_id}": set(track_ids) }

    @classmethod
    def process(
        cls,
        result: Results,
        cam_id: str,
        cam_state,      # CameraState for per-camera cooldown
        zones: list
    ) -> list[dict]:
        """
        Args:
            result:    YOLO track result
            cam_id:    camera identifier
            cam_state: CameraState for cooldown management
            zones:     list of zone dicts; uses type=="no_go_zone"

        Returns:
            List of violation alert dicts.
        """
        detections = []

        if result is None or result.boxes is None:
            return detections

        nogo_zones = [z for z in zones if z.get("type") == "no_go_zone"]
        if not nogo_zones:
            return detections

        boxes     = result.boxes
        names     = result.names
        track_ids = boxes.id
        h, w      = result.orig_shape
        sx, sy    = w / 1280.0, h / 720.0

        # Scale polygons to inference frame dimensions
        scaled_nogo_zones = []
        for zone in nogo_zones:
            polygon = zone.get("polygon", [])
            if len(polygon) < 3:
                continue
            scaled_poly = [[int(pt[0]*sx), int(pt[1]*sy)] for pt in polygon]
            
            # Create a mask for exact intersection check
            mask = np.zeros((h, w), dtype=np.uint8)
            pts = np.array(scaled_poly, np.int32).reshape((-1, 1, 2))
            cv2.fillPoly(mask, [pts], 1)
            
            scaled_nogo_zones.append({
                "id": zone.get("id", zone.get("name", "zone")),
                "name": zone.get("name", "No-Go Zone"),
                "polygon": scaled_poly,
                "mask": mask
            })

        # Track IDs inside each zone on this frame
        current_presence = {zone["id"]: set() for zone in scaled_nogo_zones}

        for i in range(len(boxes)):
            cls_id   = int(boxes.cls[i].item())
            cls_name = names.get(cls_id, "unknown")
            if cls_name not in PERSON_CLASSES:
                continue

            conf     = float(boxes.conf[i].item())
            xyxy     = boxes.xyxy[i].tolist()
            track_id = int(track_ids[i].item()) if track_ids is not None else -(i + 1)

            # Bounding box bounds (clamped to image dimensions)
            xmin = max(0, int(xyxy[0]))
            ymin = max(0, int(xyxy[1]))
            xmax = min(w, int(xyxy[2]))
            ymax = min(h, int(xyxy[3]))

            # Handle degenerate boxes
            if xmax <= xmin or ymax <= ymin:
                continue

            for zone in scaled_nogo_zones:
                # If any pixel in the bounding box overlaps with the polygon mask
                if zone["mask"][ymin:ymax, xmin:xmax].any():
                    current_presence[zone["id"]].add(track_id)

                    state_key = f"{cam_id}_{zone['id']}"
                    if state_key not in cls._in_zone:
                        cls._in_zone[state_key] = set()

                    # Trigger alert ONLY when entering (newly added to set)
                    if track_id not in cls._in_zone[state_key]:
                        # Edge trigger!
                        cam_num = cam_id.replace("cam_0", "").replace("cam_", "")
                        detections.append({
                            "feature":   "no_go_zone",
                            "class":     "person",
                            "confidence": round(conf, 3),
                            "bbox":      [int(v) for v in xyxy],
                            "cam_id":    cam_id,
                            "track_id":  track_id,
                            "zone_name": zone["name"],
                            "in_zone":   True,
                            "message":   f"Unauthorized Entry Detected in Restricted Zone - Camera {cam_num}"
                        })
                        logger.warning(
                            f"[{cam_id}] 🚫 No-Go Zone VIOLATION | "
                            f"track={track_id} zone='{zone['name']}'"
                        )

        # Update persistent presence state for all zones on this camera
        for zone in scaled_nogo_zones:
            state_key = f"{cam_id}_{zone['id']}"
            cls._in_zone[state_key] = current_presence[zone["id"]]

        return detections
