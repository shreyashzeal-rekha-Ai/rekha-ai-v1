"""
feature_logic/abandoned_object.py
---------------------------------
Abandoned / Left Luggage Detection — Phase 4.

Detects stationary, unattended bags (Backpack, Handbag, Suitcase)
reusing the SHARED YOLO person model (yolo11x.pt) with zero extra VRAM.

Supported COCO luggage classes:
  24 = backpack
  26 = handbag
  28 = suitcase

Logic:
  - Bounding boxes are tracked across frames by LuggageTracker.
  - An item is flagged as abandoned if:
    1. It remains stationary (movement < 20 pixels) for more than X seconds.
    2. No person is within 150 pixels of its centroid (attended check).
"""

import os
import math
import time
import logging
from collections import deque
from datetime import datetime, timezone, timedelta

# Enforce Kolkata / IST timezone (UTC +05:30)
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

logger = logging.getLogger("feature_logic.abandoned_object")

LUGGAGE_CLASSES = {
    24: "backpack",
    26: "handbag",
    28: "suitcase",
}
LUGGAGE_CLASS_IDS = set(LUGGAGE_CLASSES.keys())

DEFAULT_TIMEOUT_S = 300  # 5 minutes default
DEFAULT_CONF = 0.50
ALERT_COOLDOWN_S = 60.0
STATIONARY_THRESHOLD_PX = 20.0
PROXIMITY_THRESHOLD_PX = 150.0

# Global states
_trackers: dict = {}
_last_alert_time: dict = {}


def _point_in_polygon(px: float, py: float, polygon: list) -> bool:
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


class LuggageTracker:
    def __init__(self, alpha=0.8, max_missed=15):
        self.alpha = alpha
        self.max_missed = max_missed
        self.tracks = {}
        self.next_id = 1

    def update(self, detections, current_time):
        matched_detections = set()
        matched_tracks = set()

        for track in self.tracks.values():
            track["missed"] += 1

        # 1. IoU Matching
        for det_idx, det in enumerate(detections):
            best_track_id = None
            best_iou = 0.3
            for track_id, track in self.tracks.items():
                if track["cls"] != det["cls"]:
                    continue
                iou = self._get_iou(track["box"], det["box"])
                if iou > best_iou:
                    best_iou = iou
                    best_track_id = track_id

            if best_track_id is not None and best_track_id not in matched_tracks:
                track = self.tracks[best_track_id]
                track["box"] = self._ema(det["box"], track["box"])
                track["conf"] = det["conf"]
                track["missed"] = 0
                track["seen_count"] += 1
                matched_tracks.add(best_track_id)
                matched_detections.add(det_idx)

        # 2. Centroid distance matching fallback
        for det_idx, det in enumerate(detections):
            if det_idx in matched_detections:
                continue
            best_track_id = None
            best_dist = 80.0
            det_cx = (det["box"][0] + det["box"][2]) / 2.0
            det_cy = (det["box"][1] + det["box"][3]) / 2.0

            for track_id, track in self.tracks.items():
                if track_id in matched_tracks or track["cls"] != det["cls"]:
                    continue
                track_cx = (track["box"][0] + track["box"][2]) / 2.0
                track_cy = (track["box"][1] + track["box"][3]) / 2.0
                dist = math.sqrt((det_cx - track_cx) ** 2 + (det_cy - track_cy) ** 2)
                if dist < best_dist:
                    best_dist = dist
                    best_track_id = track_id

            if best_track_id is not None:
                track = self.tracks[best_track_id]
                track["box"] = self._ema(det["box"], track["box"])
                track["conf"] = det["conf"]
                track["missed"] = 0
                track["seen_count"] += 1
                matched_tracks.add(best_track_id)
                matched_detections.add(det_idx)

        # 3. Create new tracks
        for det_idx, det in enumerate(detections):
            if det_idx in matched_detections:
                continue
            cx = (det["box"][0] + det["box"][2]) / 2.0
            cy = (det["box"][1] + det["box"][3]) / 2.0
            self.tracks[self.next_id] = {
                "id": self.next_id,
                "box": det["box"],
                "cls": det["cls"],
                "conf": det["conf"],
                "missed": 0,
                "seen_count": 1,
                "first_seen": current_time,
                "stationary_start": current_time,
                "last_pos": (cx, cy),
                "unattended_start": None,
                "alert_fired": False,
                "last_alert_time": 0.0,
            }
            self.next_id += 1

        # Remove dead tracks
        for track_id in list(self.tracks.keys()):
            if self.tracks[track_id]["missed"] > self.max_missed:
                del self.tracks[track_id]

        return self.tracks

    def _get_iou(self, box1, box2):
        xi1 = max(box1[0], box2[0])
        yi1 = max(box1[1], box2[1])
        xi2 = min(box1[2], box2[2])
        yi2 = min(box1[3], box2[3])
        inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = a1 + a2 - inter
        return inter / union if union > 0 else 0.0

    def _ema(self, new_box, old_box):
        return [
            self.alpha * new_box[i] + (1 - self.alpha) * old_box[i]
            for i in range(4)
        ]


class AbandonedObjectDetector:

    @staticmethod
    def process(result, cam_id: str, cam_config: dict) -> list[dict]:
        alerts = []
        if result is None or result.boxes is None:
            return alerts

        # Config parameters
        conf_thresh = float(cam_config.get("abandoned_confidence", DEFAULT_CONF))
        timeout = int(cam_config.get("abandoned_timeout_seconds", DEFAULT_TIMEOUT_S))
        mode = cam_config.get("abandoned_object_mode", "full_frame")

        raw_zones = []
        if mode == "zone":
            raw_zones = [z for z in cam_config.get("zones", []) if z.get("type") == "abandoned_object"]

        boxes = result.boxes
        xyxy = boxes.xyxy.cpu().numpy().tolist()
        confs = boxes.conf.cpu().numpy().tolist()
        clss = boxes.cls.cpu().numpy().astype(int).tolist()

        h, w = result.orig_shape
        sx, sy = w / 1280.0, h / 720.0

        current_time = time.time()

        # Scale zone polygons
        scaled_zones = []
        for zone in raw_zones:
            poly = zone.get("polygon", [])
            if len(poly) >= 3:
                scaled_zones.append({
                    "name": zone.get("name", "Abandoned Zone"),
                    "poly": [[p[0] * sx, p[1] * sy] for p in poly]
                })

        # Separate person and luggage detections
        person_centroids = []
        luggage_dets = []

        for i in range(len(boxes)):
            cls_id = clss[i]
            conf = confs[i]
            box = xyxy[i]
            cx = (box[0] + box[2]) / 2.0
            cy = (box[1] + box[3]) / 2.0

            if cls_id == 0:  # person
                person_centroids.append((cx, cy))
            elif cls_id in LUGGAGE_CLASS_IDS and conf >= conf_thresh:
                # If zones exist, check if luggage is inside any zone
                in_zone = False
                zone_name = None
                if scaled_zones:
                    for sz in scaled_zones:
                        if _point_in_polygon(cx, cy, sz["poly"]):
                            in_zone = True
                            zone_name = sz["name"]
                            break
                else:
                    in_zone = True  # full frame check if no zones drawn

                if in_zone:
                    luggage_dets.append({
                        "box": box,
                        "cls": cls_id,
                        "conf": conf,
                        "zone_name": zone_name
                    })

        # Update tracker
        if cam_id not in _trackers:
            _trackers[cam_id] = LuggageTracker()
        tracker = _trackers[cam_id]
        tracks = tracker.update(luggage_dets, current_time)

        # Process tracks for stationary & unattended checks
        for track_id, track in tracks.items():
            if track["missed"] > 0:
                continue

            t_box = track["box"]
            cx = (t_box[0] + t_box[2]) / 2.0
            cy = (t_box[1] + t_box[3]) / 2.0

            # 1. Stationary check
            last_cx, last_cy = track["last_pos"]
            dist_moved = math.sqrt((cx - last_cx) ** 2 + (cy - last_cy) ** 2)

            if dist_moved >= STATIONARY_THRESHOLD_PX:
                # Reset stationary timer since it moved
                track["stationary_start"] = current_time
                track["last_pos"] = (cx, cy)
                track["alert_fired"] = False  # re-enable alerts if it moves

            # Calculate stationary elapsed time
            stat_elapsed = current_time - track["stationary_start"]

            # 2. Attended check
            min_person_dist = float("inf")
            for px, py in person_centroids:
                d = math.sqrt((cx - px) ** 2 + (cy - py) ** 2)
                if d < min_person_dist:
                    min_person_dist = d

            is_unattended = (min_person_dist >= PROXIMITY_THRESHOLD_PX)

            if is_unattended:
                if track["unattended_start"] is None:
                    track["unattended_start"] = current_time
            else:
                track["unattended_start"] = None
                track["alert_fired"] = False  # reset alert if someone returns to it

            # Calculate unattended elapsed time
            unatt_elapsed = 0.0
            if track["unattended_start"] is not None:
                unatt_elapsed = current_time - track["unattended_start"]

            # Calculate final abandoned duration (must be both stationary AND unattended)
            abandoned_duration = min(stat_elapsed, unatt_elapsed) if is_unattended else 0.0

            # 3. Fire Alert
            if is_unattended and abandoned_duration >= timeout:
                if not track["alert_fired"] or (current_time - track["last_alert_time"] >= ALERT_COOLDOWN_S):
                    vname = LUGGAGE_CLASSES[track["cls"]]
                    zname = luggage_dets[0]["zone_name"] if luggage_dets else None
                    z_str = f" in '{zname}'" if zname else ""
                    msg = f"Abandoned Object Alert: Unattended {vname} detected{z_str} (Stationary: {int(abandoned_duration)}s)"

                    alerts.append({
                        "feature": "abandoned_object",
                        "class": vname,
                        "confidence": round(track["conf"], 3),
                        "bbox": [int(v) for v in track["box"]],
                        "cam_id": cam_id,
                        "unattended_duration": int(abandoned_duration),
                        "message": msg,
                        "severity": "HIGH",
                        "luggage_type": vname,
                    })

                    track["alert_fired"] = True
                    track["last_alert_time"] = current_time

        return alerts

    @staticmethod
    def get_display_boxes(cam_id: str) -> list[dict]:
        boxes = []
        if cam_id in _trackers:
            current_time = time.time()
            for track_id, track in _trackers[cam_id].tracks.items():
                if track["missed"] == 0:
                    vname = LUGGAGE_CLASSES[track["cls"]]
                    
                    # Calculate active stationary duration
                    stat_elapsed = current_time - track["stationary_start"]
                    unatt_elapsed = 0.0
                    if track["unattended_start"] is not None:
                        unatt_elapsed = current_time - track["unattended_start"]
                    
                    is_unattended = (track["unattended_start"] is not None)
                    abandoned_duration = min(stat_elapsed, unatt_elapsed) if is_unattended else 0.0
                    
                    label = f"{vname.capitalize()} #{track_id}"
                    if abandoned_duration > 0.0:
                        label += f" (Left: {int(abandoned_duration)}s)"
                    elif is_unattended:
                        label += " (Unattended)"
                    else:
                        label += " (Attended)"

                    # Choose a custom color severity state if needed
                    boxes.append({
                        "box": [int(v) for v in track["box"]],
                        "label": label,
                        "conf": track["conf"],
                        "is_abandoned": (abandoned_duration >= 10.0) # highlight if left more than 10s
                    })
        return boxes


def reset_camera(cam_id: str):
    if cam_id in _trackers:
        _trackers[cam_id] = LuggageTracker()
    logger.info(f"[{cam_id}] Abandoned object detector state reset.")
