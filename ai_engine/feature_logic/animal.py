"""
feature_logic/animal.py
------------------------
Animal Detection — Phase 2.

Detects animals from the SHARED YOLO person model (yolo11x.pt).
Zero extra VRAM: model is already loaded for person detection;
we simply expand the class filter to include animal COCO class IDs.

Supported COCO animals (yolo11x.pt native):
  14=bird   15=cat    16=dog     17=horse  18=sheep
  19=cow    20=elephant  21=bear  22=zebra  23=giraffe

Limitation:
  Tigers, lions, oxen, wolves etc. are NOT in the COCO-80 dataset
  so yolo11x.pt does NOT detect them. A specialised wildlife model
  would be required for those species (future Phase 5/6 upgrade).
  Note: ox/bull may occasionally be detected as "cow" (class 19)
  due to visual similarity.

Modes (set per-camera in cameras.json as "animal_detection_mode"):
  "full_frame" (default) — alert on any animal visible anywhere
  "zone"                 — alert only when animal enters a drawn zone

Configuration keys in cameras.json:
  "animal_detection_mode": "full_frame" | "zone"
  "animal_confidence":     float (default 0.40)
"""

import logging
import threading

logger = logging.getLogger("feature_logic.animal")

# ── COCO class IDs the shared person model supports ───────────────────────────
ANIMAL_CLASSES: dict[int, str] = {
    14: "bird",
    15: "cat",
    16: "dog",
    17: "horse",
    18: "sheep",
    19: "cow",
    20: "elephant",
    21: "bear",
    22: "zebra",
    23: "giraffe",
}
ANIMAL_CLASS_IDS: set[int] = set(ANIMAL_CLASSES.keys())

# ── Severity per animal type ──────────────────────────────────────────────────
# Dangerous / large animals = higher severity so operators act faster
ANIMAL_SEVERITY: dict[str, str] = {
    "bear":     "CRITICAL",   # dangerous
    "elephant": "CRITICAL",   # dangerous
    "horse":    "HIGH",       # livestock escape / road hazard
    "cow":      "HIGH",       # livestock escape / road hazard
    "sheep":    "MEDIUM",
    "zebra":    "MEDIUM",
    "giraffe":  "MEDIUM",
    "dog":      "LOW",        # common, usually harmless
    "cat":      "LOW",
    "bird":     "LOW",
}

# Default confidence threshold (overridable per camera in cameras.json)
DEFAULT_CONF = 0.40


# ── Geometry helper ───────────────────────────────────────────────────────────

def _point_in_polygon(px: float, py: float, polygon: list) -> bool:
    """Ray-casting algorithm: True if point (px, py) is inside polygon."""
    n = len(polygon)
    inside = False
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


# ── Main detector class ───────────────────────────────────────────────────────

class AnimalDetector:
    """
    Stateless animal detector — call AnimalDetector.process() each inference frame.

    Reads from the raw YOLO person-model result BEFORE PersonTracker.update()
    filters it to class-0-only.  This is why process() must be called on the
    raw result, not the tracker output.
    """

    @staticmethod
    def process(result, cam_id: str, cam_config: dict) -> list[dict]:
        """
        Parameters
        ----------
        result     : raw YOLO Results object from model.predict()
                     (contains person + animal boxes when classes=[0, 14..23])
        cam_id     : camera identifier string
        cam_config : full camera config dict from cameras.json

        Returns
        -------
        list[dict] — alert detection dicts for alert_engine.process()
        Each dict:
          {
            "feature":    "animal_detection",
            "class":      str,    # animal name e.g. "dog"
            "confidence": float,
            "bbox":       [x1, y1, x2, y2],  # in YOLO inference space
            "cam_id":     str,
            "in_zone":    bool,
            "zone_name":  str | None,
            "severity":   str,   # "CRITICAL" / "HIGH" / "MEDIUM" / "LOW"
            "message":    str,
          }
        """
        detections: list[dict] = []

        if result is None or result.boxes is None:
            return detections

        # Per-camera config
        mode        = cam_config.get("animal_detection_mode", "full_frame")
        conf_thresh = float(cam_config.get("animal_confidence", DEFAULT_CONF))

        # Collect animal zones (type="animal_detection") for zone mode
        raw_zones = [z for z in cam_config.get("zones", [])
                     if z.get("type") == "animal_detection"]

        boxes = result.boxes
        names = result.names  # YOLO {class_id: class_name} map

        # Scale zone polygons from canvas space (1280×720) → inference frame space
        h, w = result.orig_shape
        sx, sy = w / 1280.0, h / 720.0
        scaled_zones = []
        for zone in raw_zones:
            poly = zone.get("polygon", [])
            if len(poly) >= 3:
                scaled_zones.append({
                    "name":    zone.get("name", "Animal Zone"),
                    "polygon": [[int(p[0] * sx), int(p[1] * sy)] for p in poly],
                })

        # ── Process each detected box ─────────────────────────────────────────
        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i].item())

            # Only process animal class IDs — skip person (0) and all others
            if cls_id not in ANIMAL_CLASS_IDS:
                continue

            conf = float(boxes.conf[i].item())
            if conf < conf_thresh:
                continue

            xyxy        = boxes.xyxy[i].tolist()
            animal_name = ANIMAL_CLASSES.get(cls_id, "animal")

            # Centroid for zone check
            cx = (xyxy[0] + xyxy[2]) / 2.0
            cy = (xyxy[1] + xyxy[3]) / 2.0

            in_zone   = False
            zone_name = None

            if mode == "zone":
                if not scaled_zones:
                    # Zone mode but no zones defined → skip this camera
                    logger.debug(
                        f"[AnimalDetector] [{cam_id}] Zone mode enabled but "
                        f"no animal_detection zones defined — skipping"
                    )
                    continue
                for zone in scaled_zones:
                    if _point_in_polygon(cx, cy, zone["polygon"]):
                        in_zone   = True
                        zone_name = zone["name"]
                        break
                if not in_zone:
                    continue   # zone mode: animal outside all zones → ignore

            # full_frame mode: all detections pass through
            severity = ANIMAL_SEVERITY.get(animal_name, "MEDIUM")

            logger.info(
                f"[AnimalDetector] [{cam_id}] 🐾 {animal_name.upper()} detected "
                f"conf={conf:.2f} severity={severity} "
                f"zone={zone_name or 'full_frame'}"
            )

            detections.append({
                "feature":    "animal_detection",
                "class":      animal_name,
                "confidence": round(conf, 3),
                "bbox":       [int(v) for v in xyxy],
                "cam_id":     cam_id,
                "in_zone":    in_zone,
                "zone_name":  zone_name,
                "severity":   severity,
                "message":    f"{animal_name.capitalize()} detected",
            })

        return detections
