"""
feature_logic/vehicle.py
------------------------
Vehicle Counting & Detection — Phase 3.

Detects and counts vehicles (Bicycle, Car, Motorcycle, Bus, Truck)
reusing the SHARED YOLO person model (yolo11x.pt) with zero extra VRAM.

Supported COCO vehicles:
  1 = bicycle
  2 = car
  3 = motorcycle
  5 = bus
  7 = truck

Modes:
  "full_frame"  — alert when count exceeds threshold (default 10)
  "line_cross"  — count vehicle crossings over a defined line
  "both"        — run both presence counting and line crossing (default)
"""

import os
import json
import math
import time
import logging
from collections import deque
from datetime import datetime, timezone, timedelta

# Enforce Kolkata / IST timezone (UTC +05:30)
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

logger = logging.getLogger("feature_logic.vehicle")

VEHICLE_CLASSES = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}
VEHICLE_CLASS_IDS = set(VEHICLE_CLASSES.keys())

# Default settings
DEFAULT_THRESHOLD = 10
DEFAULT_CONF = 0.45
CONGESTION_COOLDOWN_S = 60.0

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COUNTS_FILE = os.path.join(_ROOT, "vehicle_counts.json")

# Global persistence states
_counts: dict = {}
_reset_dates: dict = {}
_trackers: dict = {}
_last_congestion_alert: dict = {}
_last_write = 0.0


def _load_counts():
    try:
        if not os.path.exists(COUNTS_FILE):
            return
        with open(COUNTS_FILE) as f:
            data = json.load(f)
        for cam_id, c in data.items():
            _counts[cam_id] = {
                "total": c.get("total", {"in": 0, "out": 0}),
                "by_type": c.get("by_type", {
                    vname: {"in": 0, "out": 0} for vname in VEHICLE_CLASSES.values()
                })
            }
            if c.get("last_reset_date"):
                _reset_dates[cam_id] = c["last_reset_date"]
    except Exception as e:
        logger.warning(f"Error loading vehicle counts: {e}")


def _write_counts(force=False):
    global _last_write
    now = time.time()
    if not force and now - _last_write < 1.0:
        return
    _last_write = now
    payload = {
        cam_id: {
            "total": c["total"],
            "by_type": c["by_type"],
            "last_reset_date": _reset_dates.get(cam_id, ""),
        }
        for cam_id, c in _counts.items()
    }
    try:
        with open(COUNTS_FILE, "w") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.warning(f"Error writing vehicle counts: {e}")


_load_counts()


def _signed_dist(px, py, lx1, ly1, lx2, ly2) -> float:
    dx, dy = lx2 - lx1, ly2 - ly1
    L = math.sqrt(dx * dx + dy * dy)
    if L < 1e-6:
        return 0.0
    return ((dx * (py - ly1)) - (dy * (px - lx1))) / L


def _segments_intersect(p1, p2, p3, p4) -> bool:
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def _scale_line(line, frame_w, frame_h):
    sx = frame_w / 1280.0
    sy = frame_h / 720.0
    return (
        float(line[0][0]) * sx,
        float(line[0][1]) * sy,
        float(line[1][0]) * sx,
        float(line[1][1]) * sy,
    )


class VehicleTracker:
    def __init__(self, alpha=0.8, max_missed=10):
        self.alpha = alpha
        self.max_missed = max_missed
        self.tracks = {}
        self.next_id = 1

    def update(self, detections):
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
                cx = (track["box"][0] + track["box"][2]) / 2.0
                cy = (track["box"][1] + track["box"][3]) / 2.0
                track["trajectory"].append((cx, cy))
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
                cx = (track["box"][0] + track["box"][2]) / 2.0
                cy = (track["box"][1] + track["box"][3]) / 2.0
                track["trajectory"].append((cx, cy))
                matched_tracks.add(best_track_id)
                matched_detections.add(det_idx)

        # 3. Create new tracks
        for det_idx, det in enumerate(detections):
            if det_idx in matched_detections:
                continue
            cx = (det["box"][0] + det["box"][2]) / 2.0
            cy = (det["box"][1] + det["box"][3]) / 2.0
            traj = deque(maxlen=5)
            traj.append((cx, cy))
            self.tracks[self.next_id] = {
                "id": self.next_id,
                "box": det["box"],
                "cls": det["cls"],
                "conf": det["conf"],
                "missed": 0,
                "seen_count": 1,
                "trajectory": traj,
                "crossed": False,
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


class VehicleDetector:

    @staticmethod
    def process(result, cam_id: str, cam_config: dict) -> list[dict]:
        alerts = []
        if result is None or result.boxes is None:
            return alerts

        # Config parameters
        mode = cam_config.get("vehicle_detection_mode", "both")
        conf_thresh = float(cam_config.get("vehicle_confidence", DEFAULT_CONF))
        threshold = int(cam_config.get("vehicle_count_threshold", DEFAULT_THRESHOLD))
        invert = bool(cam_config.get("footfall_invert", False))

        boxes = result.boxes
        xyxy = boxes.xyxy.cpu().numpy().tolist()
        confs = boxes.conf.cpu().numpy().tolist()
        clss = boxes.cls.cpu().numpy().astype(int).tolist()

        # Filter detections for vehicles
        vehicle_dets = []
        for i in range(len(boxes)):
            if clss[i] not in VEHICLE_CLASS_IDS:
                continue
            if confs[i] >= conf_thresh:
                vehicle_dets.append({
                    "box": xyxy[i],
                    "cls": clss[i],
                    "conf": confs[i]
                })

        # Update tracker
        if cam_id not in _trackers:
            _trackers[cam_id] = VehicleTracker()
        tracker = _trackers[cam_id]
        tracks = tracker.update(vehicle_dets)

        # 1. Line crossing detection
        if mode in ("line_cross", "both"):
            line = cam_config.get("counting_line")
            if line and len(line) == 2:
                # Setup counts dict for camera
                if cam_id not in _counts:
                    _counts[cam_id] = {
                        "total": {"in": 0, "out": 0},
                        "by_type": {vname: {"in": 0, "out": 0} for vname in VEHICLE_CLASSES.values()}
                    }
                    _reset_dates[cam_id] = datetime.now(IST).strftime("%Y-%m-%d")

                h, w = result.orig_shape
                lx1, ly1, lx2, ly2 = _scale_line(line, w, h)

                for track_id, track in tracks.items():
                    if track["crossed"] or len(track["trajectory"]) < 2:
                        continue

                    # Bounding box coordinates
                    t_box = track["box"]
                    cx = (t_box[0] + t_box[2]) / 2.0
                    cy = (t_box[1] + t_box[3]) / 2.0

                    traj = track["trajectory"]
                    old_cx, old_cy = traj[0]

                    # Segment oldest -> current
                    if _segments_intersect((old_cx, old_cy), (cx, cy), (lx1, ly1), (lx2, ly2)):
                        # Crossing direction
                        cur_side = 1 if _signed_dist(cx, cy, lx1, ly1, lx2, ly2) >= 0 else -1
                        prev_side = 1 if _signed_dist(old_cx, old_cy, lx1, ly1, lx2, ly2) >= 0 else -1

                        if cur_side != prev_side:
                            went_positive = (prev_side == -1 and cur_side == 1)
                            went_negative = (prev_side == 1 and cur_side == -1)

                            if invert:
                                went_positive, went_negative = went_negative, went_positive

                            direction = None
                            if went_positive:
                                direction = "in"
                            elif went_negative:
                                direction = "out"

                            if direction:
                                track["crossed"] = True
                                vclass_id = track["cls"]
                                vname = VEHICLE_CLASSES[vclass_id]

                                # Increment counters
                                _counts[cam_id]["total"][direction] += 1
                                _counts[cam_id]["by_type"][vname][direction] += 1
                                _write_counts()

                                total_in = _counts[cam_id]["total"]["in"]
                                total_out = _counts[cam_id]["total"]["out"]
                                class_in = _counts[cam_id]["by_type"][vname]["in"]
                                class_out = _counts[cam_id]["by_type"][vname]["out"]

                                alerts.append({
                                    "feature": "vehicle_detection",
                                    "class": vname,
                                    "confidence": round(track["conf"], 3),
                                    "bbox": [int(v) for v in track["box"]],
                                    "cam_id": cam_id,
                                    "direction": direction,
                                    "vehicle_type": vname,
                                    "message": f"{vname.capitalize()} Crossed Line ({direction.upper()}). Type: IN={class_in}/OUT={class_out}. Total: IN={total_in}/OUT={total_out}",
                                    "severity": "LOW"
                                })

        # 2. Presence detection (full frame congestion check)
        if mode in ("full_frame", "both"):
            total_active_vehicles = len(vehicle_dets)
            if total_active_vehicles >= threshold:
                now = time.time()
                last_alert = _last_congestion_alert.get(cam_id, 0.0)
                if now - last_alert >= CONGESTION_COOLDOWN_S:
                    counts_breakdown = {}
                    for det in vehicle_dets:
                        vname = VEHICLE_CLASSES[det["cls"]]
                        counts_breakdown[vname] = counts_breakdown.get(vname, 0) + 1

                    breakdown_str = ", ".join([f"{count} {name}s" for name, count in counts_breakdown.items()])
                    msg = f"Congestion Alert: {total_active_vehicles} vehicles present ({breakdown_str})"

                    severity = "HIGH" if total_active_vehicles >= threshold * 1.5 else "MEDIUM"

                    target_box = vehicle_dets[0]["box"] if vehicle_dets else [0, 0, 0, 0]
                    target_conf = vehicle_dets[0]["conf"] if vehicle_dets else 0.50
                    target_cls = VEHICLE_CLASSES[vehicle_dets[0]["cls"]] if vehicle_dets else "car"

                    alerts.append({
                        "feature": "vehicle_detection",
                        "class": target_cls,
                        "confidence": round(target_conf, 3),
                        "bbox": [int(v) for v in target_box],
                        "cam_id": cam_id,
                        "message": msg,
                        "severity": severity,
                        "vehicle_counts": counts_breakdown,
                        "is_congestion": True
                    })
                    _last_congestion_alert[cam_id] = now

        return alerts

    @staticmethod
    def get_display_boxes(cam_id: str) -> list[dict]:
        boxes = []
        if cam_id in _trackers:
            for track_id, track in _trackers[cam_id].tracks.items():
                if track["missed"] == 0:
                    vclass_id = track["cls"]
                    vname = VEHICLE_CLASSES[vclass_id]
                    boxes.append({
                        "box": [int(v) for v in track["box"]],
                        "label": f"{vname.capitalize()} #{track_id}",
                        "conf": track["conf"]
                    })
        return boxes


def reset_counts(cam_id: str):
    if cam_id in _counts:
        _counts[cam_id] = {
            "total": {"in": 0, "out": 0},
            "by_type": {vname: {"in": 0, "out": 0} for vname in VEHICLE_CLASSES.values()}
        }
    if cam_id in _trackers:
        _trackers[cam_id] = VehicleTracker()
    _reset_dates[cam_id] = datetime.now(IST).strftime("%Y-%m-%d")
    _write_counts(force=True)
    logger.info(f"[{cam_id}] Vehicle counters explicitly reset to 0.")
