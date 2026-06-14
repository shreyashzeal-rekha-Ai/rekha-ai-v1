"""
feature_logic/anpr.py
---------------------
Automatic Number Plate Recognition (ANPR) — Phase 5.

Detects and reads vehicle license plates using a custom YOLOv8 plate detector
model and EasyOCR. Works in both full-frame and zone-restricted modes.
"""

import os
import re
import math
import time
import logging
import threading
from collections import deque, Counter
import cv2
import numpy as np

logger = logging.getLogger("feature_logic.anpr")

# Default confidence and settings
DEFAULT_CONF = 0.40
VALID_STATE_CODES = {
    'AN', 'AP', 'AR', 'AS', 'BR', 'CH', 'CG', 'DD', 'DL', 'GA', 'GJ', 'HR', 'HP', 'JK', 'JH', 'KA', 'KL', 'LA', 'LD',
    'MP', 'MH', 'MN', 'ML', 'MZ', 'NL', 'OD', 'PB', 'PY', 'RJ', 'SK', 'TN', 'TS', 'TR', 'UP', 'UK', 'UA', 'WB'
}

# Global states
_trackers: dict = {}
_reader = None
_reader_lock = threading.Lock()


def get_ocr_reader():
    """Lazily load EasyOCR reader singleton inside camera threads."""
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                try:
                    import easyocr
                    logger.info("[ANPR] Initializing EasyOCR Reader on GPU...")
                    # gpu=True uses PyTorch CUDA backend
                    _reader = easyocr.Reader(['en'], gpu=True, verbose=False)
                    logger.info("[ANPR] ✅ EasyOCR Reader successfully loaded.")
                except Exception as e:
                    logger.error(f"[ANPR] ❌ Failed to load EasyOCR: {e}")
    return _reader


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


def enhance_plate(crop) -> np.ndarray:
    """Enhance crop area to improve OCR text extraction accuracy."""
    if crop is None or crop.size == 0:
        return crop

    # 1. Grayscale
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # 2. Resize / Upscale (if it's small)
    h, w = gray.shape[:2]
    if w < 150 or h < 50:
        gray = cv2.resize(gray, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)

    # 3. CLAHE contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    return enhanced


def correct_indian_plate(text: str) -> str:
    """Correct common OCR character substitutions based on Indian plate syntax positions."""
    # Strip spaces and non-alphanumeric chars
    text = re.sub(r'[^A-Z0-9]', '', text.upper())
    
    num_to_let = {'0': 'O', '1': 'I', '8': 'B', '5': 'S', '2': 'Z'}
    let_to_num = {'O': '0', 'I': '1', 'B': '8', 'S': '5', 'Z': '2', 'G': '6', 'T': '1', 'Q': '0'}
    
    chars = list(text)
    n = len(chars)
    
    if n < 8 or n > 10:
        return text  # Skip standardisation if length doesn't fit standard plates
        
    # Positions 0, 1: State Code (Letters only)
    for i in (0, 1):
        if chars[i] in num_to_let:
            chars[i] = num_to_let[chars[i]]
            
    # Positions 2, 3: District Code (Numbers only)
    for i in (2, 3):
        if chars[i] in let_to_num:
            chars[i] = let_to_num[chars[i]]
            
    if n == 10:  # AA 00 AA 0000
        # Positions 4, 5: Letters only
        for i in (4, 5):
            if chars[i] in num_to_let:
                chars[i] = num_to_let[chars[i]]
        # Positions 6, 7, 8, 9: Numbers only
        for i in (6, 7, 8, 9):
            if chars[i] in let_to_num:
                chars[i] = let_to_num[chars[i]]
                
    elif n == 9:  # AA 00 A 0000
        # Position 4: Letter only
        if chars[4] in num_to_let:
            chars[4] = num_to_let[chars[4]]
        # Positions 5, 6, 7, 8: Numbers only
        for i in (5, 6, 7, 8):
            if chars[i] in let_to_num:
                chars[i] = let_to_num[chars[i]]
                
    elif n == 8:  # AA 00 0000
        # Positions 4, 5, 6, 7: Numbers only
        for i in (4, 5, 6, 7):
            if chars[i] in let_to_num:
                chars[i] = let_to_num[chars[i]]
                
    return "".join(chars)


def validate_indian_plate(text: str) -> bool:
    """Validate standard Indian plate layout structure."""
    if len(text) < 8 or len(text) > 10:
        return False
    
    # Check if state code is valid
    state_code = text[:2]
    if state_code not in VALID_STATE_CODES:
        return False
        
    # Standard format regex matching
    pattern = r'^[A-Z]{2}[0-9]{2}[A-Z]{0,2}[0-9]{4}$'
    return bool(re.match(pattern, text))


class PlateTracker:
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
                if track_id in matched_tracks:
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
            self.tracks[self.next_id] = {
                "id": self.next_id,
                "box": det["box"],
                "conf": det["conf"],
                "missed": 0,
                "seen_count": 1,
                "plate_history": deque(maxlen=10),
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


class ANPRDetector:

    @staticmethod
    def process(result, cam_id: str, cam_config: dict, display_frame) -> list[dict]:
        alerts = []
        if result is None or result.boxes is None or display_frame is None or display_frame.size == 0:
            return alerts

        # Config parameters
        conf_thresh = float(cam_config.get("anpr_confidence", DEFAULT_CONF))
        raw_zones = []
        mode = cam_config.get("anpr_mode", "full_frame")
        if mode == "zone":
            raw_zones = [z for z in cam_config.get("zones", []) if z.get("type") == "anpr"]

        boxes = result.boxes
        xyxy = boxes.xyxy.cpu().numpy().tolist()
        confs = boxes.conf.cpu().numpy().tolist()

        h, w = display_frame.shape[:2]
        # YOLO runs on 640x360 inference frame space
        infer_h, infer_w = result.orig_shape
        scale_x = w / float(infer_w)
        scale_y = h / float(infer_h)

        current_time = time.time()

        # Scale zone polygons (canvas coordinates 1280x720 -> display_frame w x h)
        scaled_zones = []
        sx_zone, sy_zone = w / 1280.0, h / 720.0
        for zone in raw_zones:
            poly = zone.get("polygon", [])
            if len(poly) >= 3:
                scaled_zones.append({
                    "name": zone.get("name", "ANPR Zone"),
                    "poly": [[p[0] * sx_zone, p[1] * sy_zone] for p in poly]
                })

        plate_dets = []

        for i in range(len(boxes)):
            conf = confs[i]
            if conf < conf_thresh:
                continue
            box = xyxy[i]
            
            # Centroid in display frame space
            cx = ((box[0] + box[2]) / 2.0) * scale_x
            cy = ((box[1] + box[3]) / 2.0) * scale_y

            # Zone boundary check
            in_zone = False
            zone_name = None
            if scaled_zones:
                for sz in scaled_zones:
                    if _point_in_polygon(cx, cy, sz["poly"]):
                        in_zone = True
                        zone_name = sz["name"]
                        break
            else:
                in_zone = True

            if in_zone:
                plate_dets.append({
                    "box": box,
                    "conf": conf,
                    "zone_name": zone_name
                })

        # Update tracker
        if cam_id not in _trackers:
            _trackers[cam_id] = PlateTracker()
        tracker = _trackers[cam_id]
        tracks = tracker.update(plate_dets, current_time)

        # Process tracks
        for track_id, track in tracks.items():
            if track["missed"] > 0:
                continue

            # --- OPTIMIZATION 1: Skip OCR if plate already confirmed ---
            if "confirmed_plate" in track:
                continue

            # --- OPTIMIZATION 2: Skip OCR if max attempts reached (prevents CPU/GPU spin on unreadable plates) ---
            ocr_attempts = track.get("ocr_attempts", 0)
            if ocr_attempts >= 10:
                # Limit fallback attempts to once every 15 frames
                if track["seen_count"] % 15 != 0:
                    continue

            # --- OPTIMIZATION 3: Throttle OCR frequency (only run every 3rd frame) ---
            if track["seen_count"] % 3 != 0:
                continue

            t_box = track["box"]
            
            # Crop boundaries from original high-resolution display frame
            x1 = max(0, int(t_box[0] * scale_x))
            y1 = max(0, int(t_box[1] * scale_y))
            x2 = min(w, int(t_box[2] * scale_x))
            y2 = min(h, int(t_box[3] * scale_y))

            if x2 <= x1 or y2 <= y1:
                continue

            crop = display_frame[y1:y2, x1:x2]
            enhanced = enhance_plate(crop)

            if enhanced is not None and enhanced.size > 0:
                try:
                    reader = get_ocr_reader()
                    if reader is not None:
                        # Record attempt
                        track["ocr_attempts"] = ocr_attempts + 1
                        ocr_results = reader.readtext(enhanced)
                        if ocr_results:
                            # Join and clean detected text
                            raw_text = "".join([res[1] for res in ocr_results])
                            clean_text = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
                            corrected = correct_indian_plate(clean_text)
                            
                            if len(corrected) >= 8 and len(corrected) <= 10:
                                track["plate_history"].append(corrected)
                except Exception as e:
                    logger.error(f"[ANPR] OCR error: {e}")

            # Voting & Alerting
            if track["plate_history"]:
                counts = Counter(track["plate_history"])
                best_plate, vote_count = counts.most_common(1)[0]
                
                # Check minimum vote count threshold to prevent transient errors
                if vote_count >= 3 and validate_indian_plate(best_plate):
                    track["confirmed_plate"] = best_plate
                    
                    if not track["alert_fired"]:
                        zname = track.get("zone_name")
                        z_str = f" in '{zname}'" if zname else ""
                        msg = f"ANPR Alert: Vehicle detected with plate {best_plate}{z_str}"

                        alerts.append({
                            "feature": "anpr",
                            "class": "license_plate",
                            "confidence": round(track["conf"], 3),
                            "bbox": [int(v) for v in track["box"]],
                            "cam_id": cam_id,
                            "message": msg,
                            "severity": "LOW",
                            "plate_text": best_plate,
                        })
                        track["alert_fired"] = True
                        track["last_alert_time"] = current_time

        return alerts

    @staticmethod
    def get_display_boxes(cam_id: str) -> list[dict]:
        boxes = []
        if cam_id in _trackers:
            for track_id, track in _trackers[cam_id].tracks.items():
                if track["missed"] == 0:
                    label = f"Plate #{track_id}"
                    if "confirmed_plate" in track:
                        label = f"{track['confirmed_plate']}"
                    elif track["plate_history"]:
                        label = f"Reading... ({track['plate_history'][-1]})"
                    else:
                        label = "Plate"
                        
                    boxes.append({
                        "box": [int(v) for v in track["box"]],
                        "label": label,
                        "conf": track["conf"],
                    })
        return boxes


def reset_camera(cam_id: str):
    if cam_id in _trackers:
        _trackers[cam_id] = PlateTracker()
    logger.info(f"[{cam_id}] ANPR detector state reset.")
