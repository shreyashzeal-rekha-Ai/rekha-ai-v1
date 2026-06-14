"""
feature_logic/intrusion.py
---------------------------
Person Intrusion detector (v1 — ACTIVE).
Detects persons in frame and checks if they are inside
any restricted zone polygon defined in cameras.json.
"""

import logging
import numpy as np
from ultralytics.engine.results import Results

logger = logging.getLogger("feature_logic.intrusion")

PERSON_CLASSES = {"person", "Person", "PERSON"}


def _point_in_polygon(px: float, py: float, polygon: list[list[int]]) -> bool:
    """
    Ray-casting algorithm to check if point (px, py)
    is inside a polygon defined as [[x,y], [x,y], ...].
    """
    n      = len(polygon)
    inside = False
    xinters = 0.0
    x1, y1 = polygon[0]
    for i in range(1, n + 1):
        x2, y2 = polygon[i % n]
        if py > min(y1, y2):
            if py <= max(y1, y2):
                if px <= max(x1, x2):
                    if y1 != y2:
                        xinters = (py - y1) * (x2 - x1) / (y2 - y1) + x1
                    if x1 == x2 or px <= xinters:
                        inside = not inside
        x1, y1 = x2, y2
    return inside


class IntrusionDetector:
    """
    Processes YOLO person-detection results and checks intrusion into zones.
    """

    @staticmethod
    def process(result: Results, cam_id: str, zones: list[dict]) -> list[dict]:
        """
        Args:
            result:  ultralytics Results object from person model inference
            cam_id:  camera identifier
            zones:   list of zone dicts from cameras.json

        Returns:
            List of detection dicts. Each dict has the matched zone info
            if the person is inside a restricted zone.
            {
                "feature":    "intrusion",
                "class":      "person",
                "confidence": float,
                "bbox":       [x1, y1, x2, y2],
                "cam_id":     str,
                "in_zone":    bool,
                "zone_name":  str | None
            }
        """
        detections = []

        if result is None or result.boxes is None:
            return detections

        boxes = result.boxes
        names = result.names

        for i in range(len(boxes)):
            cls_id     = int(boxes.cls[i].item())
            cls_name   = names.get(cls_id, "unknown")
            confidence = float(boxes.conf[i].item())
            xyxy       = boxes.xyxy[i].tolist()

            if cls_name not in PERSON_CLASSES:
                continue

            # Bottom-center of bounding box = feet position
            foot_x = (xyxy[0] + xyxy[2]) / 2
            foot_y = xyxy[3]

            # Scale zones to match inference frame coordinates
            scaled_zones = []
            for zone in zones:
                if not zone.get("alert_on_intrusion", False):
                    continue
                polygon = zone.get("polygon", [])
                if len(polygon) < 3:
                    continue
                h, w = result.orig_shape
                sx, sy = w / 1280.0, h / 720.0
                scaled_poly = [[int(pt[0]*sx), int(pt[1]*sy)] for pt in polygon]
                scaled_zones.append({
                    "name": zone.get("name", "Unknown Zone"),
                    "polygon": scaled_poly
                })

            in_zone    = False
            zone_name  = None

            for zone in scaled_zones:
                polygon = zone["polygon"]
                if _point_in_polygon(foot_x, foot_y, polygon):
                    in_zone   = True
                    zone_name = zone["name"]
                    logger.debug(
                        f"[{cam_id}] 🚨 Person in zone '{zone_name}' "
                        f"feet=({foot_x:.0f},{foot_y:.0f}) conf={confidence:.2f}"
                    )
                    break

            detections.append({
                "feature":    "intrusion",
                "class":      "person",
                "confidence": round(confidence, 3),
                "bbox":       [int(v) for v in xyxy],
                "cam_id":     cam_id,
                "in_zone":    in_zone,
                "zone_name":  zone_name
            })

        return detections
