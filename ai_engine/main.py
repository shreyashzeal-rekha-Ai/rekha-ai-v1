"""
main.py
-------
Expert CCTV — AI Engine v1

Changes vs original:
  • Parallel feature processing — each feature runs in its own thread per frame
  • Frame annotation — draws YOLO boxes + zone overlays on processed frame
  • Shared frame JPEG — writes latest annotated frame to clips/latest_frame.jpg
    so the Flask backend can stream it to the dashboard
  • Hot-reload cameras.json — polls every 5 s; no restart needed after Settings Apply
"""

import os
import sys
import cv2
import json
import queue
import logging
import signal
import threading
import collections
import time
from datetime import datetime, timezone, timedelta
import numpy as np

# ── Strictly enforce Kolkata / IST timezone (UTC +05:30) ──────────────────────
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# ── resolve project root ─────────────────────────────────────────────
ROOT_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(ROOT_DIR, '.env'))

# ── logging ──────────────────────────────────────────────────────────
LOG_DIR = os.path.join(ROOT_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, 'ai_engine.log'), encoding='utf-8'),
    ]
)
logger = logging.getLogger("main")

# ── local imports ────────────────────────────────────────────────────
from inference_engine import ModelRegistry, run_inference
from camera_reader    import CameraReader
from camera_state     import CameraState
from motion_filter    import MotionFilter
from alert_engine     import AlertEngine
from clip_recorder    import ClipRecorder
from watchdog         import Watchdog
from person_tracker   import PersonTracker

from feature_logic import (
    FireSmokeDetector,
    IntrusionDetector,
    LoiteringDetector,
    FootfallCounter,
    CrowdDetector,
    MissingPersonDetector,
    NoGoZoneDetector,
    PerimeterDetector,
    PersonalMonitoringDetector,
    TamperingDetector,
    WeaponDetector,
    CriminalFaceDetector,
    AnimalDetector,            # Phase 2
    mp_reset_zone,
    mp_reset_camera,
)
from feature_logic.schedule_utils import is_schedule_active

# ── paths / config ───────────────────────────────────────────────────
CAMERAS_JSON     = os.path.join(ROOT_DIR, 'cameras.json')
CLIPS_DIR        = os.path.join(ROOT_DIR, 'clips')
LATEST_FRAME     = os.path.join(CLIPS_DIR, 'latest_frame.jpg')
FPS_LIMIT        = 30
CLIP_BUFFER_LEN  = 100
CONFIG_RELOAD_S  = 1       # how often to check cameras.json for changes (seconds)
SAVE_CLIPS       = os.getenv("SAVE_CLIPS", "True").strip().lower() in ("true", "1", "yes")

os.makedirs(CLIPS_DIR, exist_ok=True)

# ── Feature colour palette (BGR) for annotations ────────────────────
FEAT_COLOR = {
    "intrusion":           (0, 110, 255),   # orange
    "no_go_zone":          (0, 23, 255),    # red
    "loitering":           (0, 214, 255),   # yellow
    "crowd":               (0, 255, 118),   # green
    "missing_person":      (255, 64, 224),  # purple
    "personal_monitoring": (255, 229, 0),   # cyan
    "footfall":            (255, 176, 0),   # blue
    "perimeter":           (130, 64, 255),  # pink
    "fire_smoke":          (0, 61, 255),    # red-orange
    "tampering":           (164, 0, 255),   # violet
    "person":              (100, 120, 255), # light red  ← person detection
    "weapon_detection":    (0, 0, 255),     # bright red  🔫
    "criminal_face":       (0, 165, 255),   # orange-red  🚨
    "animal_detection":    (34, 200, 34),   # green  🐾 Phase 2
}


# ════════════════════════════════════════════════════════════════════
# Config hot-reload
# ════════════════════════════════════════════════════════════════════

class ConfigWatcher:
    """
    Watches cameras.json for file modification time changes.
    Thread-safe: call get_cameras() from any thread to get the
    always-up-to-date config.
    """
    def __init__(self, path: str):
        self._path   = path
        self._lock   = threading.RLock()
        self._cameras: list[dict] = []
        self._mtime  = 0.0
        self._load()

    def _load(self):
        try:
            mtime = os.path.getmtime(self._path)
            with open(self._path, 'r') as f:
                data = json.load(f)
            with self._lock:
                self._cameras = data.get("cameras", [])
                self._mtime   = mtime
            logger.info(f"[Config] Loaded {len(self._cameras)} camera(s)."
                        f" Features: "
                        + str({c['id']: c.get('features', []) for c in self._cameras}))
        except Exception as e:
            logger.error(f"[Config] Failed to load cameras.json: {e}")

    def poll(self):
        """Call this periodically to check for changes."""
        try:
            mtime = os.path.getmtime(self._path)
            if mtime != self._mtime:
                logger.info("[Config] 🔄 cameras.json changed — reloading...")
                self._load()
        except Exception:
            pass

    def get_cameras(self) -> list[dict]:
        with self._lock:
            return list(self._cameras)


# ════════════════════════════════════════════════════════════════════
# Frame annotation
# ════════════════════════════════════════════════════════════════════

def annotate_frame(frame, cam_config: dict, results: dict, active_features: list,
                   infer_w: int = 640, infer_h: int = 360):
    """
    Draws on a COPY of frame:
      - Zone borders (no fill — keeps video clear)
      - Footfall gate line: thick red vertical line + IN/OUT/OCC HUD on frame
      - Person boxes: GREEN if inside gate, WHITE if outside
      - Fire detection boxes
      - HUD overlay + timestamp

    All saved coordinates are in 1280x720 canvas space.
    We scale them to actual frame dimensions here.
    """
    out = frame.copy()
    h, w = out.shape[:2]

    # ── Coordinate scaling: canvas(1280x720) → actual frame ──────────
    CANVAS_W, CANVAS_H = 1280.0, 720.0
    sx = w / CANVAS_W
    sy = h / CANVAS_H

    def sp(pts):   return [[int(p[0]*sx), int(p[1]*sy)] for p in pts]
    def sp1(pt):   return (int(pt[0]*sx), int(pt[1]*sy))

    # ── Zone borders only (no fill) ───────────────────────────────────
    # Border thickness scales with frame width so it looks consistent after
    # resize to 1280×720 regardless of DVR stream resolution (main vs sub).
    _border_thick = max(1, round(2 * w / 1280))
    _dot_radius   = max(2, round(4 * w / 1280))
    for zone in cam_config.get("zones", []):
        raw_pts = zone.get("polygon")
        if not raw_pts or len(raw_pts) < 3:
            continue
        pts   = sp(raw_pts)
        feat  = zone.get("type", "")
        color = FEAT_COLOR.get(feat, (200, 200, 200))
        arr   = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(out, [arr], isClosed=True, color=color, thickness=_border_thick)
        for p in pts:
            cv2.circle(out, tuple(p), _dot_radius, color, -1)
        bx = min(p[0] for p in pts)
        by = max(4, min(p[1] for p in pts) - 4)
        label = zone.get("name", feat)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
        cv2.rectangle(out, (bx-2, by-th-4), (bx+tw+4, by+2), color, -1)
        cv2.putText(out, label, (bx+1, by-2), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0,0,0), 1, cv2.LINE_AA)

    # ── Footfall gate line + IN/OUT HUD ──────────────────────────────
    cl = cam_config.get("counting_line")
    if cl and len(cl) == 2 and "footfall" in active_features:
        pt1 = sp1(cl[0])
        pt2 = sp1(cl[1])

        # Cyan border zone on the LEFT (inside) side
        cv2.rectangle(out, (0, 0), (pt1[0], h),
                      (0, 210, 210), 1)

        # Thick RED gate line (like reference image)
        cv2.line(out, pt1, pt2, (0, 0, 220), 4, cv2.LINE_AA)
        # Cyan outline on top
        cv2.line(out, pt1, pt2, (220, 210, 0), 1, cv2.LINE_AA)

        # ── Big IN/OUT counter HUD on frame (like reference image) ───
        from feature_logic.footfall import get_counts
        fc = get_counts(cam_config.get("id", "cam_01"))
        hud_lines = [
            (f"IN : {fc['count_in']}",  (0, 220, 90)),
            (f"OUT: {fc['count_out']}", (0, 80, 220)),
            (f"NOW: {fc['occupancy']}", (200, 200, 0)),
        ]
        # Black background box
        cv2.rectangle(out, (0, 0), (200, 85), (0, 0, 0), -1)
        for li, (txt, col) in enumerate(hud_lines):
            cv2.putText(out, txt, (8, 24 + li*26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.72, col, 2, cv2.LINE_AA)

    # ── Perimeter line ────────────────────────────────────────────────
    pl = cam_config.get("perimeter_line")
    if pl and len(pl) == 2 and "perimeter" in active_features:
        color = FEAT_COLOR["perimeter"]
        pt1 = sp1(pl[0])
        pt2 = sp1(pl[1])
        cv2.line(out, pt1, pt2, color, 2, cv2.LINE_AA)
        cv2.putText(out, "Perimeter", (pt1[0]+5, pt1[1]-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    # ── Person bounding boxes ─────────────────────────────────────────
    # Coords from PersonTracker are in inference (infer_w×infer_h) space.
    # Scale up to the actual display frame dimensions.
    # BOX_TRIM: shave 4 px on each side so the box hugs the person outline.
    BOX_TRIM = 4
    person_res = results.get("person_tracked")
    if person_res is not None:
        # Scale: inference → display frame
        px = w / infer_w
        py = h / infer_h

        boxes = getattr(person_res, "boxes", None)
        if boxes is not None:
            try:
                xyxy      = boxes.xyxy.cpu().numpy()
                ids       = boxes.id
                track_ids = ids.cpu().numpy().astype(int) if ids is not None else [None]*len(xyxy)
                for (x1, y1, x2, y2), tid in zip(xyxy, track_ids):
                    # Scale from inference space to display space, then trim inward
                    x1 = int(x1 * px) + BOX_TRIM
                    y1 = int(y1 * py) + BOX_TRIM
                    x2 = int(x2 * px) - BOX_TRIM
                    y2 = int(y2 * py) - BOX_TRIM
                    if x2 <= x1 or y2 <= y1:   # skip degenerate boxes
                        continue
                    c = FEAT_COLOR["person"]
                    cv2.rectangle(out, (x1, y1), (x2, y2), c, 2)
                    label = f"Person #{tid}" if tid is not None else "Person"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                    cv2.rectangle(out, (x1, y1 - th - 10), (x1 + tw + 6, y1), c, -1)
                    cv2.putText(out, label, (x1 + 3, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
            except Exception:
                pass

    # ── Fire / Smoke boxes (drawn from safe serialized plain-Python dicts) ────
    # fire_display_boxes is populated after every AI frame and reused safely
    # on interleaved (non-AI) frames — no GPU tensors here.
    for box in results.get("fire_display_boxes", []):
        x1, y1, x2, y2 = box["bbox"]
        # Scale coords from 640×360 inference space → actual frame size
        x1 = int(x1 * sx * (CANVAS_W / 640))
        y1 = int(y1 * sy * (CANVAS_H / 360))
        x2 = int(x2 * sx * (CANVAS_W / 640))
        y2 = int(y2 * sy * (CANVAS_H / 360))
        c  = FEAT_COLOR["fire_smoke"]
        label = box.get("label", "FIRE 🔥")
        conf  = box.get("confidence", 0)
        frames = box.get("frames", 0)
        # Thick outer box
        cv2.rectangle(out, (x1, y1), (x2, y2), c, 3)
        # Inner accent box
        cv2.rectangle(out, (x1+2, y1+2), (x2-2, y2-2), (0, 120, 255), 1)
        # Label background
        lbl_text = f"{label}  {conf*100:.0f}%"
        (tw, th), _ = cv2.getTextSize(lbl_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(out, (x1, y1 - th - 10), (x1 + tw + 8, y1), c, -1)
        cv2.putText(out, lbl_text, (x1 + 4, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

    # ── Animal detection boxes ───────────────────────────────────────
    # Coords are in YOLO inference space (640×360); scale same as person boxes.
    if "animal_detection" in active_features:
        c   = FEAT_COLOR["animal_detection"]
        apx = w / infer_w
        apy = h / infer_h
        for det in results.get("animal_display_boxes", []):
            x1, y1, x2, y2 = det["bbox"]
            x1 = int(x1 * apx); y1 = int(y1 * apy)
            x2 = int(x2 * apx); y2 = int(y2 * apy)
            sev   = det.get("severity", "MEDIUM")
            aname = det.get("class", "animal").upper()
            conf  = det.get("confidence", 0)
            # Thicker box for dangerous animals
            thick = 3 if sev == "CRITICAL" else 2
            cv2.rectangle(out, (x1, y1), (x2, y2), c, thick)
            lbl = f"🐾 {aname}  {conf*100:.0f}%"
            (tw, th), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(out, (x1, y1 - th - 10), (x1 + tw + 8, y1), c, -1)
            cv2.putText(out, lbl, (x1 + 4, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    # ── Weapon boxes ────────────────────────────────────────────────────
    # Coords from weapon model are in inference (infer_w×infer_h) space — scale up.
    weapon_res = results.get("weapon_boxes")
    if weapon_res and "weapon_detection" in active_features:
        c = FEAT_COLOR["weapon_detection"]
        wpx = w / infer_w
        wpy = h / infer_h
        for det in weapon_res:
            x1, y1, x2, y2 = det["bbox"]
            x1 = int(x1 * wpx); y1 = int(y1 * wpy)
            x2 = int(x2 * wpx); y2 = int(y2 * wpy)
            cv2.rectangle(out, (x1, y1), (x2, y2), c, 3)
            lbl = f"{det['class'].upper()} {det['confidence']*100:.0f}%"
            cv2.rectangle(out, (x1, y1-22), (x1+len(lbl)*9, y1), c, -1)
            cv2.putText(out, lbl, (x1+3, y1-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)

    # ── Criminal face boxes ────────────────────────────────────────────
    # face_recognition coords are in inference space — scale up.
    if "criminal_face" in active_features:
        from feature_logic.criminal_face import get_last_faces
        cam_id_ann = cam_config.get("id", "cam_01")
        fpx = w / infer_w
        fpy = h / infer_h
        for (top, right, bottom, left, name) in get_last_faces(cam_id_ann):
            c = (0, 220, 0) if name != "Unknown" else (80, 80, 80)
            if name == "Unknown":
                continue   # don't clutter with unknown faces
            top    = int(top    * fpy); right  = int(right  * fpx)
            bottom = int(bottom * fpy); left   = int(left   * fpx)
            cv2.rectangle(out, (left, top), (right, bottom), c, 2)
            cv2.rectangle(out, (left, bottom), (right, bottom+24), c, -1)
            cv2.putText(out, f"WATCHLIST: {name}", (left+4, bottom+17),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1, cv2.LINE_AA)

    # ── Active features HUD (right side) ─────────────────────────────
    hud_y = 20
    for feat in active_features:
        if feat == "footfall": continue
        color = FEAT_COLOR.get(feat, (200, 200, 200))
        cv2.putText(out, f"> {feat.replace('_',' ').upper()}",
                    (8, hud_y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.42, color, 1, cv2.LINE_AA)
        hud_y += 16

    # Timestamp
    ts_str = datetime.now(IST).strftime("%Y-%m-%d  %H:%M:%S")
    cv2.putText(out, ts_str, (w - 195, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)
    return out


# ════════════════════════════════════════════════════════════════════
# Schedule-aware active feature resolver
# ════════════════════════════════════════════════════════════════════

# Map: feature name → cam_config schedule key
# Features NOT listed here have no top-level schedule (always active).
_FEATURE_SCHEDULE_KEY: dict[str, str] = {
    "loitering":           "loitering_schedule",
    "crowd":               "crowd_schedule",
    "footfall":            "footfall_schedule",
    "perimeter":           "perimeter_schedule",
    "missing_person":      "missing_person_schedule",
    "personal_monitoring": "personal_monitoring_schedule",
    "tampering":           "tampering_schedule",
    # intrusion / no_go_zone → per-zone schedules checked inside the detector
    # fire_smoke / weapon_detection / criminal_face → no schedule concept
}


def _get_active_features_now(cam_config: dict) -> set:
    """
    Returns the SUBSET of enabled features that are active RIGHT NOW
    based on their configured schedule.

    Rules:
      • Features with no schedule entry (or schedule.enabled=False) → always active.
      • Features whose schedule window excludes current time        → EXCLUDED.
      • intrusion / no_go_zone use PER-ZONE schedules:
          - If AT LEAST ONE zone is active  → feature is included (YOLO runs).
          - If ALL zones are off-schedule   → feature is EXCLUDED (YOLO skipped).
      • fire_smoke / weapon_detection / criminal_face → no schedule, always active.

    This ensures the YOLO person model is skipped entirely when no person-based
    feature is currently scheduled — zero GPU waste during off-hours.
    """
    active: set[str] = set()
    zones = cam_config.get("zones", [])

    for feat in cam_config.get("features", []):

        # ── intrusion / no_go_zone: schedule lives inside each zone ───────────
        if feat in ("intrusion", "no_go_zone"):
            # Collect zones that belong to this feature type
            feat_zones = [z for z in zones if z.get("type") == feat]
            if not feat_zones:
                # No zones defined at all → always include (detector handles gracefully)
                active.add(feat)
            elif any(is_schedule_active(z.get("schedule")) for z in feat_zones):
                # At least one zone is currently active → YOLO must run
                active.add(feat)
            else:
                # EVERY zone is off-schedule → skip YOLO entirely for this feature
                logger.debug(
                    f"[Schedule] cam={cam_config.get('id')} feat={feat} "
                    f"— ALL zones OFF-SCHEDULE — skipping YOLO + logic entirely"
                )
            continue

        # ── All other features: schedule at camera-config level ────────────────
        sched_key = _FEATURE_SCHEDULE_KEY.get(feat)
        if sched_key is None:
            # No schedule concept for this feature → always active
            active.add(feat)
        else:
            sched = cam_config.get(sched_key)
            if is_schedule_active(sched):
                active.add(feat)
            else:
                logger.debug(
                    f"[Schedule] cam={cam_config.get('id')} feat={feat} "
                    f"is OFF-SCHEDULE — skipping inference + logic entirely"
                )
    return active


# ════════════════════════════════════════════════════════════════════
# Per-frame feature processing (sequential within one call so results
# are shared, fired in parallel ACROSS cameras with ThreadPoolExecutor)
# ════════════════════════════════════════════════════════════════════

def process_camera_frame(
    frame,                          # 640×360 inference frame (fed to YOLO)
    display_frame,                  # original DVR-resolution frame (annotated for streaming)
    cam_config:    dict,
    registry:      ModelRegistry,
    motion_filter: MotionFilter,
    alert_engine:  AlertEngine,
    clip_recorder: ClipRecorder,
    clip_buffer:   collections.deque,
    cam_state:     CameraState,
    tampering_det,
    tracker,
    fire_lock:   threading.Lock = None,
    person_lock: threading.Lock = None,
) -> np.ndarray:
    """
    Full pipeline for ONE frame from ONE camera.
    `frame`         — 640×360 inference copy (fast YOLO input).
    `display_frame` — original DVR-resolution frame used for annotation;
                      annotations are drawn at full resolution so no
                      upscaling blur is introduced.
    Returns (annotated_display_frame, results_dict).
    fire_lock / person_lock are passed into run_inference so each model
    acquires only ITS lock — cameras never block each other unnecessarily.
    """
    cam_id       = cam_config["id"]
    features     = cam_config.get("features", [])   # full list — used for annotation
    features_set = set(features)
    zones        = cam_config.get("zones", [])
    fps          = cam_config.get("fps_limit", FPS_LIMIT)

    # ── Features active RIGHT NOW (schedule-aware) ───────────────────
    # Only features in this set trigger inference + logic this frame.
    # Features outside their schedule window are fully skipped —
    # no YOLO call, no zone math, no timer updates — zero CPU/GPU waste.
    features_active_now = _get_active_features_now(cam_config)

    # ── Inference — per-camera fire quality settings ────────────────────────
    # cam-specific override: fire_infer_size and fire_confidence in cameras.json
    # All other cameras keep standard 640-wide inference (saves VRAM).
    fire_infer_size = cam_config.get("fire_infer_size", 640)    # e.g. 1280 for cam_03
    fire_conf_override = cam_config.get("fire_confidence", None)   # e.g. 0.55

    if "fire_smoke" in features_active_now and fire_infer_size > 640:
        # Build a higher-res fire frame from the full DVR frame
        fire_h = int(fire_infer_size * 9 / 16)  # maintain 16:9 aspect
        fire_frame_hires = cv2.resize(display_frame, (fire_infer_size, fire_h))
    else:
        fire_frame_hires = frame   # standard 640x360 for all other cameras

    # Pass only ACTIVE features to run_inference — this is the key GPU saving:
    # if all person-based features are off-schedule, the YOLO person model
    # is not called at all for this frame.
    results = run_inference(
        registry, frame, list(features_active_now),
        fire_lock=fire_lock, person_lock=person_lock,
        fire_conf=fire_conf_override,
        fire_imgsz=fire_infer_size,
        fire_frame=fire_frame_hires if fire_infer_size > 640 else None,
    )
    # HSV validation must use the SAME frame the fire model processed
    # (coordinates from YOLO are in that frame's pixel space)
    _fire_frame_for_hsv = fire_frame_hires

    # ── Serialize fire display boxes immediately after inference ─────────────
    # Must happen BEFORE annotate_frame so interleaved frames can safely reuse
    # plain Python dicts instead of stale GPU tensor objects.
    if "fire_smoke" in features_active_now:
        fire_raw = results.get("fire_smoke")
        # Pass the matching frame so HSV colour validation can reject sunlight
        fire_alert_dets = (
            FireSmokeDetector.process(fire_raw, cam_id, frame=_fire_frame_for_hsv)
            if fire_raw is not None else []
        )
        # Store safe plain-Python display boxes (reused on every non-AI frame)
        results["fire_display_boxes"] = FireSmokeDetector.get_display_boxes(cam_id)
        # Store alert detections separately so feature block below can use them
        results["fire_alert_dets"] = fire_alert_dets

    # Keep rolling clip buffer
    if SAVE_CLIPS:
        clip_buffer.append(frame.copy())

    person_res = results.get("person_tracked")

    # ── Phase 2: Animal detection ────────────────────────────────
    # MUST run BEFORE tracker.update() because the tracker filters to
    # class 0 (person) only, removing all animal boxes from the result.
    if "animal_detection" in features_active_now and person_res is not None:
        results["animal_display_boxes"] = AnimalDetector.process(
            person_res, cam_id, cam_config
        )
    else:
        results["animal_display_boxes"] = []

    person_res = tracker.update(person_res, is_inference_frame=True, device=registry.device)
    results["person_tracked"] = person_res

    # ── Annotate BEFORE firing alerts so snapshots show boxes + IDs ──────────
    # annotate_frame draws zone overlays, person bounding boxes with track IDs,
    # fire/weapon boxes, and the HUD timestamp onto the full DVR-resolution frame.
    # We do this FIRST so the annotated frame can be passed to alert_engine and
    # saved as the alert snapshot — giving operators a fully-labelled image.
    ih, iw = frame.shape[:2]   # actual inference dimensions (should be 640×360)
    annotated = annotate_frame(display_frame, cam_config, results, features,
                               infer_w=iw, infer_h=ih)
    # Scale to 1280×720 for consistent snapshot size (same as dashboard stream)
    annotated_snap = cv2.resize(annotated, (1280, 720))

    # ── Run ONLY enabled features — sequential, zero thread overhead ──

    if "fire_smoke" in features_active_now:
        try:
            # Alert dets already computed above (with 5-frame threshold)
            dets = results.get("fire_alert_dets", [])
            if dets:
                alert_engine.process(dets, annotated_snap, cam_id, "fire_smoke")
                clip_recorder.enqueue(cam_id, "fire_smoke", list(clip_buffer), fps=fps)
        except Exception as e:
            logger.error(f"[Feature] fire_smoke: {e}")

    if "intrusion" in features_active_now and person_res:
        try:
            # Filter zones to only those whose schedule is currently active
            active_zones = [z for z in zones if is_schedule_active(z.get("schedule"))]
            dets = IntrusionDetector.process(person_res, cam_id, active_zones)
            if dets:
                alert_engine.process(dets, annotated_snap, cam_id, "intrusion")
                clip_recorder.enqueue(cam_id, "intrusion", list(clip_buffer), fps=fps)
        except Exception as e:
            logger.error(f"[Feature] intrusion: {e}")

    if "loitering" in features_active_now:
        try:
            timeout = cam_config.get("loitering_timeout_seconds", 120)
            # Pass person_res even if None, because the detector needs to tick its internal clocks
            dets = LoiteringDetector.process(person_res, cam_id, cam_state, zones, timeout_seconds=timeout, frame=frame)
            if dets:
                alert_engine.process(dets, annotated_snap, cam_id, "loitering")
                clip_recorder.enqueue(cam_id, "loitering", list(clip_buffer), fps=fps)
        except Exception as e:
            logger.error(f"[Feature] loitering: {e}")

    if "no_go_zone" in features_active_now and person_res:
        try:
            # Filter zones to only those whose schedule is currently active
            active_zones = [z for z in zones if is_schedule_active(z.get("schedule"))]
            dets = NoGoZoneDetector.process(person_res, cam_id, cam_state, active_zones)
            if dets:
                alert_engine.process(dets, annotated_snap, cam_id, "no_go_zone")
                clip_recorder.enqueue(cam_id, "no_go_zone", list(clip_buffer), fps=fps)
        except Exception as e:
            logger.error(f"[Feature] no_go_zone: {e}")

    if "crowd" in features_active_now and person_res:
        try:
            dets = CrowdDetector.process(person_res, cam_id, cam_state,
                                         max_count=cam_config.get("crowd_threshold", 10), zones=zones)
            if dets:
                alert_engine.process(dets, annotated_snap, cam_id, "crowd")
        except Exception as e:
            logger.error(f"[Feature] crowd: {e}")

    if "footfall" in features_active_now and person_res:
        try:
            line = cam_config.get("counting_line")
            if line:
                fh, fw = frame.shape[:2]
                events = FootfallCounter.process(person_res, cam_id, cam_state, line,
                                                 frame_w=fw, frame_h=fh)
                if events:
                    alert_engine.process(events, annotated_snap, cam_id, "footfall")
        except Exception as e:
            logger.error(f"[Feature] footfall: {e}")

    if "perimeter" in features_active_now and person_res:
        try:
            fh, fw = frame.shape[:2]
            # Primary perimeter line (backward compat)
            pline = cam_config.get("perimeter_line")
            if pline:
                dets = PerimeterDetector.process(person_res, cam_id, cam_state, pline,
                                                 frame_w=fw, frame_h=fh)
                if dets:
                    alert_engine.process(dets, annotated_snap, cam_id, "perimeter")
                    clip_recorder.enqueue(cam_id, "perimeter", list(clip_buffer), fps=fps)
            # Extra perimeter lines (multi-zone mode) stored in zones[] with type='perimeter'
            extra_perim_zones = [z for z in cam_config.get("zones", []) if z.get("type") == "perimeter"]
            for ez in extra_perim_zones:
                eline = ez.get("line")
                if eline and len(eline) == 2:
                    try:
                        dets = PerimeterDetector.process(person_res, cam_id, cam_state, eline,
                                                         frame_w=fw, frame_h=fh)
                        if dets:
                            alert_engine.process(dets, annotated_snap, cam_id, "perimeter")
                            clip_recorder.enqueue(cam_id, "perimeter", list(clip_buffer), fps=fps)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"[Feature] perimeter: {e}")

    if "missing_person" in features_active_now and person_res is not None:
        try:
            timeout = cam_config.get("missing_person_timeout_seconds", 30)
            target_count = cam_config.get("missing_person_target_count", 1)
            dets = MissingPersonDetector.process(
                person_res, cam_id, cam_state, zones,
                timeout_seconds=timeout,
                target_count=target_count
            )
            if dets:
                alert_engine.process(dets, annotated_snap, cam_id, "missing_person")
        except Exception as e:
            logger.error(f"[Feature] missing_person: {e}")

    if "personal_monitoring" in features_active_now and person_res is not None:
        try:
            timeout = cam_config.get("personal_monitoring_timeout_seconds", 300)
            dets = PersonalMonitoringDetector.process(person_res, cam_id, cam_state, zones, timeout_seconds=timeout)
            if dets:
                alert_engine.process(dets, annotated_snap, cam_id, "personal_monitoring")
        except Exception as e:
            logger.error(f"[Feature] personal_monitoring: {e}")

    if "weapon_detection" in features_active_now:
        try:
            dets = WeaponDetector.process(frame, cam_id, cam_state)
            if dets:
                results["weapon_boxes"] = dets
                alert_engine.process(dets, annotated_snap, cam_id, "weapon_detection")
                clip_recorder.enqueue(cam_id, "weapon_detection", list(clip_buffer), fps=fps)
        except Exception as e:
            logger.error(f"[Feature] weapon_detection: {e}")

    if "animal_detection" in features_active_now:
        try:
            dets = results.get("animal_display_boxes", [])
            if dets:
                alert_engine.process(dets, annotated_snap, cam_id, "animal_detection")
                clip_recorder.enqueue(cam_id, "animal_detection", list(clip_buffer), fps=fps)
        except Exception as e:
            logger.error(f"[Feature] animal_detection: {e}")

    if "criminal_face" in features_active_now:
        try:
            dets = CriminalFaceDetector.process(frame, cam_id, cam_state)
            if dets:
                alert_engine.process(dets, annotated_snap, cam_id, "criminal_face")
                clip_recorder.enqueue(cam_id, "criminal_face", list(clip_buffer), fps=fps)
        except Exception as e:
            logger.error(f"[Feature] criminal_face: {e}")

    if "tampering" in features_active_now:
        try:
            dets = tampering_det.process(frame, cam_state)
            if dets:
                alert_engine.process(dets, annotated_snap, cam_id, "tampering")
                clip_recorder.enqueue(cam_id, "tampering", list(clip_buffer), fps=fps)
        except Exception as e:
            logger.error(f"[Feature] tampering: {e}")

    return annotated, results

# ════════════════════════════════════════════════════════════════════
# CameraProcessor Thread
# ════════════════════════════════════════════════════════════════════

class CameraProcessor(threading.Thread):
    """
    Dedicated thread per camera to process frames asynchronously.
    """
    def __init__(
        self,
        cam_cfg: dict,
        reader: CameraReader,
        registry: ModelRegistry,
        motion_filter: MotionFilter,
        alert_engine: AlertEngine,
        clip_recorder: ClipRecorder,
        clip_buffer: collections.deque,
        cam_state: CameraState,
        tampering_det: TamperingDetector,
        shutdown_event: threading.Event,
        fire_lock:   threading.Lock,
        person_lock: threading.Lock,
    ):
        super().__init__(daemon=True, name=f"Processor-{cam_cfg['id']}")
        self.cam_cfg = cam_cfg
        self.reader = reader
        self.registry = registry
        self.motion_filter = motion_filter
        self.alert_engine = alert_engine
        self.clip_recorder = clip_recorder
        self.clip_buffer = clip_buffer
        self.cam_state = cam_state
        self.tampering_det = tampering_det
        self.shutdown_event = shutdown_event
        self.fire_lock   = fire_lock
        self.person_lock = person_lock
        self.tracker     = PersonTracker(max_missed_frames=45)  # uses default alpha=0.8 (Phase 1 fix)

        self.cid = cam_cfg["id"]
        self.frame_path = os.path.join(CLIPS_DIR, f'latest_frame_{self.cid}.jpg')
        self.frame_counter = 0
        self.last_annotated = None
        self.last_results   = {}  # last known AI detections, reused on skipped frames
        self.local_shutdown = False

    def stop(self):
        self.local_shutdown = True

    def run(self):
        fps = self.cam_cfg.get("fps_limit", FPS_LIMIT)
        delay = 1.0 / fps
        logger.info(f"[Processor-{self.cid}] Started processing thread.")

        while not self.shutdown_event.is_set() and not self.local_shutdown:
            start_time = time.time()

            frame = self.reader.get_frame(timeout=0.1)
            if frame is None:
                continue

            # Drain queue — always process newest frame only
            while not self.reader.frame_queue.empty():
                try:
                    frame = self.reader.frame_queue.get_nowait()
                except queue.Empty:
                    break

            # ── Inference frame: small copy for YOLO speed ──────────────────
            infer_frame = cv2.resize(frame, (640, 360))
            # display_frame: original DVR resolution — annotations drawn here
            display_frame = frame
            self.frame_counter += 1
            features = self.cam_cfg.get("features", [])

            # ── INFERENCE INTERLEAVING (per-camera configurable) ────────────────
            # inference_every_n in cameras.json controls how often YOLO runs:
            #   2 → 15 fps AI  (highest priority cam)
            #   3 → 10 fps AI  (medium priority cam)
            #   4 →  7.5 fps AI (lower priority cam)
            # Fallback: 2 if not set in config.
            _infer_n = self.cam_cfg.get("inference_every_n", 2)
            if self.frame_counter % _infer_n == 0:
                try:
                    annotated, self.last_results = process_camera_frame(
                        frame         = infer_frame,
                        display_frame = display_frame,
                        cam_config    = self.cam_cfg,
                        registry      = self.registry,
                        motion_filter = self.motion_filter,
                        alert_engine  = self.alert_engine,
                        clip_recorder = self.clip_recorder,
                        clip_buffer   = self.clip_buffer,
                        cam_state     = self.cam_state,
                        tampering_det = self.tampering_det,
                        tracker       = self.tracker,
                        fire_lock     = self.fire_lock,
                        person_lock   = self.person_lock,
                    )
                except Exception as e:
                    logger.error(f"[Processor-{self.cid}] Frame error: {e}", exc_info=True)
                    annotated = display_frame
            else:
                # No AI this frame — update tracker, draw smoothed boxes on fresh display_frame
                smoothed_res = self.tracker.update(None, is_inference_frame=False, device=self.registry.device)
                self.last_results["person_tracked"] = smoothed_res
                annotated = annotate_frame(
                    display_frame, self.cam_cfg, self.last_results, features,
                    infer_w=640, infer_h=360
                )

            # Normalise to 1280×720 for the dashboard (single consistent size)
            self.last_annotated = cv2.resize(annotated, (1280, 720))

            # Always write latest good frame
            if self.last_annotated is not None:
                try:
                    ok, buf = cv2.imencode(
                        '.jpg', self.last_annotated,
                        [cv2.IMWRITE_JPEG_QUALITY, 88]  # 88 = sharp, still well-compressed
                    )
                    if ok:
                        temp_path = self.frame_path + ".tmp"
                        with open(temp_path, 'wb') as fh:
                            fh.write(buf.tobytes())
                        try:
                            os.replace(temp_path, self.frame_path)
                        except OSError:
                            pass  # Ignore Windows sharing violation
                except Exception as je:
                    logger.debug(f"[Processor-{self.cid}] JPEG write error: {je}")

            # Match target FPS
            elapsed = time.time() - start_time
            sleep_time = max(0.001, delay - elapsed)
            time.sleep(sleep_time)

        logger.info(f"[Processor-{self.cid}] Thread stopped.")


# ════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════

def main():
    logger.info("=" * 60)
    logger.info("  Expert CCTV — AI Engine v1 Starting (Parallel Optimization)")
    logger.info("=" * 60)

    watcher  = ConfigWatcher(CAMERAS_JSON)
    cameras  = watcher.get_cameras()

    if not cameras:
        logger.error("No cameras defined in cameras.json. Exiting.")
        sys.exit(1)

    # Collect every feature enabled across ALL cameras
    all_features = set()
    for cam in cameras:
        all_features.update(cam.get("features", []))
    logger.info(f"[Startup] All enabled features across cameras: {all_features}")
    logger.info("[Startup] Loading only required YOLO models...")
    registry = ModelRegistry.build(all_features)

    event_queue: queue.Queue = queue.Queue(maxsize=200)
    clip_recorder = ClipRecorder()
    clip_recorder.start()
    alert_engine  = AlertEngine(event_queue)

    # ── Camera readers ───────────────────────────────────────────────
    camera_readers: list[CameraReader] = []
    for cam_cfg in cameras:
        reader = CameraReader(cam_cfg)
        reader.start()
        camera_readers.append(reader)

    # ── Per-camera state ─────────────────────────────────────────────
    motion_filters: dict[str, MotionFilter]     = {}
    clip_buffers:   dict[str, collections.deque] = {}
    cam_states:     dict[str, CameraState]       = {}
    tampering_dets: dict[str, TamperingDetector] = {}

    for cam_cfg in cameras:
        cid = cam_cfg["id"]
        motion_filters[cid]  = MotionFilter(cid)
        clip_buffers[cid]    = collections.deque(maxlen=CLIP_BUFFER_LEN)
        cam_states[cid]      = CameraState(cid)
        tampering_dets[cid]  = TamperingDetector(cid)

    watchdog = Watchdog(camera_readers)
    watchdog.start()

    _shutdown = threading.Event()
    # Two separate locks — fire & person models can now run in parallel across cameras
    fire_lock   = threading.Lock()
    person_lock = threading.Lock()

    def _handle_signal(sig, frame):
        logger.info(f"\n[Main] Signal {sig} — shutting down...")
        _shutdown.set()

    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── Start camera processing threads ──────────────────────────────
    processors: dict[str, CameraProcessor] = {}
    for cam_cfg in cameras:
        cid = cam_cfg["id"]
        reader = next((r for r in camera_readers if r.cam_id == cid), None)
        if reader is not None:
            proc = CameraProcessor(
                cam_cfg        = cam_cfg,
                reader         = reader,
                registry       = registry,
                motion_filter  = motion_filters[cid],
                alert_engine   = alert_engine,
                clip_recorder  = clip_recorder,
                clip_buffer    = clip_buffers[cid],
                cam_state      = cam_states[cid],
                tampering_det  = tampering_dets[cid],
                shutdown_event = _shutdown,
                fire_lock      = fire_lock,
                person_lock    = person_lock,
            )
            proc.start()
            processors[cid] = proc

    logger.info(f"[Startup] ✅ Ready. Cameras: {[c['id'] for c in cameras]}")
    logger.info("[Startup] Press Ctrl+C to stop.\n")

    last_config_check = time.time()

    # ════════════════════════════════════════════════════════════════
    # Main thread config reload & monitoring loop
    # ════════════════════════════════════════════════════════════════
    try:
        while not _shutdown.is_set():
            # ── Hot-reload check ─────────────────────────────────────
            if time.time() - last_config_check >= CONFIG_RELOAD_S:
                watcher.poll()
                new_cameras = watcher.get_cameras()
                
                new_cids = {c["id"] for c in new_cameras}
                old_cids = set(processors.keys())
                
                # ── 1. Stop deleted cameras ──
                for cid in (old_cids - new_cids):
                    logger.info(f"[ConfigWatcher] 🛑 Stopping camera {cid} (deleted)...")
                    if cid in processors:
                        proc = processors.pop(cid)
                        proc.stop()
                    reader = next((r for r in camera_readers if r.cam_id == cid), None)
                    if reader:
                        reader.stop()
                        camera_readers.remove(reader)
                    motion_filters.pop(cid, None)
                    clip_buffers.pop(cid, None)
                    cam_states.pop(cid, None)
                    tampering_dets.pop(cid, None)
                    mp_reset_camera(cid)   # ← clear missing-person timers
                
                # ── 2. Start added cameras ──
                for cam_cfg in new_cameras:
                    cid = cam_cfg["id"]
                    if cid not in processors:
                        logger.info(f"[ConfigWatcher] 🚀 Starting camera {cid} (newly added)...")
                        
                        motion_filters[cid]  = MotionFilter(cid)
                        clip_buffers[cid]    = collections.deque(maxlen=CLIP_BUFFER_LEN)
                        cam_states[cid]      = CameraState(cid)
                        tampering_dets[cid]  = TamperingDetector(cid)
                        
                        reader = CameraReader(cam_cfg)
                        reader.start()
                        camera_readers.append(reader)
                        
                        proc = CameraProcessor(
                            cam_cfg        = cam_cfg,
                            reader         = reader,
                            registry       = registry,
                            motion_filter  = motion_filters[cid],
                            alert_engine   = alert_engine,
                            clip_recorder  = clip_recorder,
                            clip_buffer    = clip_buffers[cid],
                            cam_state      = cam_states[cid],
                            tampering_det  = tampering_dets[cid],
                            shutdown_event = _shutdown,
                            fire_lock      = fire_lock,
                            person_lock    = person_lock,
                        )
                        proc.start()
                        processors[cid] = proc
                
                # ── 3. Update configs of existing cameras ──
                for cam_cfg in new_cameras:
                    cid = cam_cfg["id"]
                    if cid in processors:
                        reader = next((r for r in camera_readers if r.cam_id == cid), None)
                        if reader and reader.source != cam_cfg["source"]:
                            logger.info(f"[ConfigWatcher] 🔄 Source changed for {cid} to {cam_cfg['source']} — restarting reader...")
                            reader.stop()
                            camera_readers.remove(reader)
                            
                            new_reader = CameraReader(cam_cfg)
                            new_reader.start()
                            camera_readers.append(new_reader)
                            processors[cid].reader = new_reader
                        
                        # Push updated config to the running processor thread.
                        # Zone changes + timeout changes take effect immediately.
                        # NOTE: do NOT reset missing_person timers here — the
                        # polygon-hash check inside MissingPersonDetector.process()
                        # auto-detects polygon changes and resets only when needed.
                        # Resetting here every 5 s would prevent the timer ever
                        # reaching the threshold. ← was the root bug.
                        processors[cid].cam_cfg = cam_cfg

                last_config_check = time.time()

            time.sleep(1.0)

    finally:
        logger.info("[Main] Stopping threads...")
        for reader in camera_readers:
            reader.stop()
        clip_recorder.stop()
        watchdog.stop()
        logger.info("[Main] 👋 Shutdown complete.")


if __name__ == "__main__":
    main()
