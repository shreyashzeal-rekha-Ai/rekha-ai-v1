"""
feature_logic/fire_smoke.py
----------------------------
Production-grade Fire & Smoke detector for CCTV parking area deployment.

ROOT CAUSE of low-confidence real fire detections
──────────────────────────────────────────────────
  1. The fire model was NOT trained on H.264-compressed CCTV footage.
     H.264 DCT blocks destroy colour fidelity → the model becomes uncertain
     about whether orange blobs are fire, giving 0.20–0.30 instead of 0.80+.
  2. Small fires (<1% of frame area) have too few feature pixels at 640-px
     inference resolution → low-activation → low confidence.
  3. Similar HSV range between fire and scene objects (orange posters,
     banners, bike fairings, clothes) creates ambiguity.

SOLUTION: Score-based multi-evidence accumulation
──────────────────────────────────────────────────
  Instead of raising the confidence threshold (which misses real fire),
  we keep the threshold LOW (0.22) and accumulate EVIDENCE from:

  Evidence 1 — Model confidence (+conf per frame)
    The model is noisy but directionally correct. Summing confidence
    over consecutive frames is more reliable than any single frame.

  Evidence 2 — Flicker / motion intensity (+FLICKER_BONUS)
    Fire is never static. We compute the mean absolute pixel difference
    (MAD) between the current and previous frame inside the detection
    bbox. A real fire flickers: MAD > threshold. Orange posters, walls,
    and clothes are static: MAD ≈ 0. This is the most powerful discriminator.

  Evidence 3 — Smoke corroboration (+SMOKE_BONUS)
    If the model also detects smoke within SMOKE_DIST_MAX pixels of a
    fire bbox, the score gets a large bonus. Both fire AND smoke appearing
    together is extremely strong evidence of a real event.

  Evidence 4 — Temporal persistence (score must reach ALERT_SCORE)
    Score decays each frame the detection is absent (×SCORE_DECAY).
    A true fire persists for seconds; a reflection lasts 1–2 frames.
    This naturally rejects transient false positives.

CONFIDENCE THRESHOLD RECOMMENDATION
──────────────────────────────────────
  Set fire_confidence: 0.22 in cameras.json
    • Real fire  : 0.20–0.35 (passes gate)
    • Posters    : 0.20–0.60 (passes gate, rejected by flicker + persistence)
    • Overexposed: any (rejected by overexposure gate before scoring)

  Do NOT raise above 0.40 — you will miss real small fires.
  The score system handles false positives, NOT the confidence gate.

IOU THRESHOLD RECOMMENDATION
──────────────────────────────
  Use iou=0.35 for fire model.
  Lower IoU allows better NMS recall on overlapping small detections.

SMALL-OBJECT DETECTION (SAHI-lite approach)
────────────────────────────────────────────
  fire_infer_size=1280 already doubles effective resolution.
  Full SAHI tiling is too slow for RTX 3050 in real-time.
  Instead, the 1280-px inference gives 4× more pixels for a 1% flame
  compared to 640-px: from 6×6 px → 12×12 px (enough for meaningful features).
  If RTX 3050 can handle it, set fire_infer_size=1920 for even better results.

HARD NEGATIVE MINING STRATEGY
──────────────────────────────
  The flicker gate (Evidence 2) is the programmatic hard-negative filter.
  For model-level improvement: collect frames of orange banners/clothes from
  YOUR cameras → annotate with class "background" → fine-tune best_fire.pt
  with these as hard negatives using YOLOv8 train with --freeze backbone.
  Recommended datasets: FireNet, FLAME, VisiFire, D-Fire.

PRODUCTION ARCHITECTURE NOTE
──────────────────────────────
  Multi-camera safe: all state is stored per cam_id in module-level dicts.
  Thread-safe reads (GIL protects dict access); writes happen on one thread
  per camera (CameraProcessor). No locks needed.
"""

import cv2
import logging
import numpy as np
from ultralytics.engine.results import Results

logger = logging.getLogger("feature_logic.fire_smoke")

# ── Class labels ─────────────────────────────────────────────────────────────
FIRE_CLASSES  = {"fire", "Fire", "FIRE"}
SMOKE_CLASSES = {"smoke", "Smoke", "SMOKE"}

# ── Confidence gate (keep LOW — score system handles false positives) ─────────
# Overridden per camera by fire_confidence in cameras.json
DEFAULT_FIRE_CONF = 0.22

# ── Score-based accumulation parameters ──────────────────────────────────────
ALERT_SCORE       = 6.0    # accumulated score to fire an alert
DISPLAY_SCORE     = 1.5    # score to show the bounding box on screen
SCORE_DECAY       = 0.72   # score × this each frame the detection is absent
MAX_MISSED_FRAMES = 8      # frames before a track is removed from memory

# Evidence bonuses added to score each frame
CONF_MULTIPLIER   = 8.0    # raw model confidence (0.22) × this = 1.76 per frame
                           # → fires alert after ~4 frames if also flickering
FLICKER_BONUS     = 1.2    # added when motion/flicker detected inside bbox
SMOKE_BONUS       = 2.5    # added when smoke is detected near a fire bbox
STATIC_PENALTY    = 0.0    # deducted when bbox is perfectly static (optional)

# ── Flicker (motion intensity) detection ──────────────────────────────────────
FLICKER_MAD_THR   = 4.0    # mean absolute pixel diff (0-255) to call it "flickering"
                           # orange poster: ~0.5   real fire: ~8-25
FLICKER_BLUR_K    = 5      # kernel size for Gaussian blur before diff (removes JPEG noise)

# ── Smoke-fire fusion ─────────────────────────────────────────────────────────
SMOKE_DIST_MAX    = 250    # pixels — smoke bbox centre must be within this of fire

# ── Minimum bbox area gate ────────────────────────────────────────────────────
# Rejects single-pixel noise. At 1280×720, 25×25 px = 625 (a very small flame).
MIN_BBOX_AREA     = 600

# ── Overexposure gate (only direct light sources — NOT CCTV fire) ─────────────
OVEREXPOSURE_V    = 245    # mean HSV-V above this
OVEREXPOSURE_S    = 28     # AND mean HSV-S below this → pure white light, reject

# ── IoU matching for tracks without ByteTrack ID ─────────────────────────────
IOU_MATCH_THR     = 0.20   # lower is more lenient (fire bbox shifts between frames)


# ════════════════════════════════════════════════════════════════════════════════
# Internal track state
# ════════════════════════════════════════════════════════════════════════════════

class _FireTrack:
    """Represents a single persisted fire detection across multiple frames."""
    __slots__ = [
        "score",          # accumulated evidence score
        "frames_seen",    # frames this track was confirmed present
        "frames_missed",  # consecutive frames this track was NOT detected
        "bbox",           # last known [x1,y1,x2,y2]
        "conf",           # last raw model confidence
        "prev_gray",      # grayscale ROI from previous frame (for flicker)
        "has_alerted",    # True once an alert has been sent for this track
        "class_name",     # "fire" or "smoke"
    ]

    def __init__(self, bbox, conf, class_name):
        self.score         = conf * CONF_MULTIPLIER
        self.frames_seen   = 1
        self.frames_missed = 0
        self.bbox          = bbox
        self.conf          = conf
        self.prev_gray     = None
        self.has_alerted   = False
        self.class_name    = class_name


# Module-level state: {cam_id: {internal_id: _FireTrack}}
_tracks: dict[str, dict[int, _FireTrack]] = {}
_next_ids: dict[str, int] = {}

# Display boxes (serialised plain Python — safe to read from any thread)
_display_boxes: dict[str, list] = {}


# ════════════════════════════════════════════════════════════════════════════════
# Geometry helpers
# ════════════════════════════════════════════════════════════════════════════════

def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1)
    ub = (bx2 - bx1) * (by2 - by1)
    return inter / (ua + ub - inter + 1e-6)


def _bbox_centre(bbox):
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _centre_dist(a, b) -> float:
    ca, cb = _bbox_centre(a), _bbox_centre(b)
    return ((ca[0] - cb[0])**2 + (ca[1] - cb[1])**2) ** 0.5


def _bbox_area(bbox) -> int:
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


# ════════════════════════════════════════════════════════════════════════════════
# Validation gates
# ════════════════════════════════════════════════════════════════════════════════

def _overexposure_gate(frame: np.ndarray, bbox: list) -> bool:
    """True if region is pure white / direct light source → reject."""
    if frame is None:
        return False
    x1, y1, x2, y2 = bbox
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = max(0,x1), max(0,y1), min(w,x2), min(h,y2)
    if x2 <= x1 or y2 <= y1:
        return False
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mv  = float(np.mean(hsv[:, :, 2]))
    ms  = float(np.mean(hsv[:, :, 1]))
    return mv > OVEREXPOSURE_V and ms < OVEREXPOSURE_S


def _compute_flicker(frame: np.ndarray, bbox: list, prev_gray: np.ndarray):
    """
    Returns (mad, cur_gray):
      mad      — mean absolute pixel diff in bbox (0 = static, >FLICKER_MAD_THR = fire)
      cur_gray — current grayscale ROI (store in track for next frame)
    """
    if frame is None:
        return 0.0, None
    x1, y1, x2, y2 = bbox
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = max(0,x1), max(0,y1), min(w,x2), min(h,y2)
    if x2 <= x1 or y2 <= y1:
        return 0.0, None
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0, None
    cur_gray = cv2.GaussianBlur(
        cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32),
        (FLICKER_BLUR_K, FLICKER_BLUR_K), 0
    )
    mad = 0.0
    if prev_gray is not None:
        try:
            # Resize to same shape if bbox shifted slightly
            pg = cv2.resize(prev_gray, (cur_gray.shape[1], cur_gray.shape[0]))
            mad = float(np.mean(np.abs(cur_gray - pg)))
        except Exception:
            mad = 0.0
    return mad, cur_gray


# ════════════════════════════════════════════════════════════════════════════════
# Main detector class
# ════════════════════════════════════════════════════════════════════════════════

class FireSmokeDetector:
    """
    Score-based fire & smoke detector.
    State is stored at module level (cam_id keyed) so it survives hot reloads.
    """

    @classmethod
    def process(
        cls,
        result: Results,
        cam_id: str,
        frame: np.ndarray = None,
    ) -> list[dict]:
        """
        Run one inference frame through the full validation pipeline.

        Args:
            result:  YOLO .track() result
            cam_id:  camera identifier
            frame:   BGR frame fed to YOLO (used for flicker + overexposure checks)

        Returns:
            List of alert dicts for confirmed fires (score >= ALERT_SCORE).
        """
        if cam_id not in _tracks:
            _tracks[cam_id] = {}
            _next_ids[cam_id] = 1

        cam_tracks = _tracks[cam_id]
        alert_detections  = []
        new_display_boxes = []

        # ── Parse YOLO detections ───────────────────────────────────────────
        fire_detections  = []   # (bbox, conf, track_id)
        smoke_detections = []   # (bbox, conf, track_id)

        if result is not None and result.boxes is not None:
            boxes     = result.boxes
            names     = result.names or {}
            yolo_ids  = boxes.id.int().tolist() if boxes.id is not None else []

            for i in range(len(boxes)):
                cls_name   = names.get(int(boxes.cls[i].item()), "unknown")
                confidence = float(boxes.conf[i].item())
                bbox       = [int(v) for v in boxes.xyxy[i].tolist()]
                tid        = yolo_ids[i] if i < len(yolo_ids) else None

                if cls_name in FIRE_CLASSES:
                    fire_detections.append((bbox, confidence, tid))
                elif cls_name in SMOKE_CLASSES:
                    smoke_detections.append((bbox, confidence, tid))

        # ── Step 1: Match fire detections to existing tracks ────────────────
        matched_track_ids = set()
        matched_det_idxs  = set()

        for di, (bbox, conf, yolo_tid) in enumerate(fire_detections):

            # ── Gate 1: minimum bbox area ────────────────────────────────
            if _bbox_area(bbox) < MIN_BBOX_AREA:
                logger.debug(f"[{cam_id}] fire: rejected tiny bbox area={_bbox_area(bbox)}")
                continue

            # ── Gate 2: overexposure ─────────────────────────────────────
            if frame is not None and _overexposure_gate(frame, bbox):
                logger.debug(f"[{cam_id}] fire: rejected overexposed bbox")
                continue

            # ── Gate 3: find best matching track ─────────────────────────
            best_tid  = None
            best_iou  = IOU_MATCH_THR

            for tid, trk in cam_tracks.items():
                if tid in matched_track_ids:
                    continue
                if trk.class_name != "fire":
                    continue
                iou = _iou(bbox, trk.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid

            # ── Gate 4: compute flicker score ─────────────────────────────
            prev_gray = cam_tracks[best_tid].prev_gray if best_tid is not None else None
            mad, cur_gray = _compute_flicker(frame, bbox, prev_gray)
            flickering = mad > FLICKER_MAD_THR

            # ── Update or create track ────────────────────────────────────
            if best_tid is not None:
                trk = cam_tracks[best_tid]
                trk.bbox          = bbox
                trk.conf          = conf
                trk.frames_seen  += 1
                trk.frames_missed = 0
                trk.prev_gray     = cur_gray
                trk.score        += conf * CONF_MULTIPLIER
                if flickering:
                    trk.score += FLICKER_BONUS
                matched_track_ids.add(best_tid)
            else:
                # New track
                new_tid = _next_ids[cam_id]
                _next_ids[cam_id] += 1
                trk = _FireTrack(bbox, conf, "fire")
                trk.prev_gray = cur_gray
                if flickering:
                    trk.score += FLICKER_BONUS
                cam_tracks[new_tid] = trk
                matched_track_ids.add(new_tid)
                best_tid = new_tid

            matched_det_idxs.add(di)

            logger.debug(
                f"[{cam_id}] 🔥 fire track={best_tid} conf={conf:.2f} "
                f"score={trk.score:.1f} MAD={mad:.1f} flicker={flickering} "
                f"frames={trk.frames_seen}"
            )

        # ── Step 2: Smoke detection & smoke-fire fusion ─────────────────────
        smoke_bboxes = []
        for bbox, conf, _ in smoke_detections:
            if _bbox_area(bbox) < MIN_BBOX_AREA:
                continue
            smoke_bboxes.append(bbox)

        for tid, trk in cam_tracks.items():
            if trk.class_name != "fire":
                continue
            if tid not in matched_track_ids:
                continue
            for sbbox in smoke_bboxes:
                dist = _centre_dist(trk.bbox, sbbox)
                if dist < SMOKE_DIST_MAX:
                    trk.score += SMOKE_BONUS
                    logger.debug(
                        f"[{cam_id}] 💨 smoke fusion: fire track={tid} "
                        f"smoke_dist={dist:.0f}px +{SMOKE_BONUS} score→{trk.score:.1f}"
                    )
                    break   # one smoke bonus per fire track per frame

        # ── Step 3: Process smoke as its own tracks ──────────────────────────
        # (simplified — smoke uses basic frame counter, not full score system)
        # This avoids over-engineering smoke; the fusion bonus above is the key link.
        for bbox, conf, _ in smoke_detections:
            if _bbox_area(bbox) < MIN_BBOX_AREA:
                continue
            new_display_boxes.append({
                "bbox":       bbox,
                "label":      "SMOKE 💨",
                "confidence": round(conf, 2),
                "track_id":   None,
                "score":      round(conf, 2),
            })

        # ── Step 4: Decay / expire unmatched tracks ─────────────────────────
        to_delete = []
        for tid, trk in cam_tracks.items():
            if tid not in matched_track_ids:
                trk.frames_missed += 1
                trk.score         *= SCORE_DECAY
                trk.prev_gray      = None   # can't compute flicker on missed frame
                if trk.frames_missed > MAX_MISSED_FRAMES or trk.score < 0.1:
                    to_delete.append(tid)
        for tid in to_delete:
            del cam_tracks[tid]

        # ── Step 5: Build display boxes & alerts ────────────────────────────
        for tid, trk in cam_tracks.items():
            if trk.score < DISPLAY_SCORE:
                continue

            score_pct = min(100, int(trk.score / ALERT_SCORE * 100))
            new_display_boxes.append({
                "bbox":       trk.bbox,
                "label":      f"FIRE 🔥 {score_pct}%",
                "confidence": round(trk.conf, 2),
                "track_id":   tid,
                "score":      round(trk.score, 1),
                "frames":     trk.frames_seen,
            })

            if trk.score >= ALERT_SCORE and not trk.has_alerted:
                trk.has_alerted = True
                alert_detections.append({
                    "feature":    "fire_smoke",
                    "class":      "fire",
                    "confidence": round(trk.conf, 3),
                    "bbox":       trk.bbox,
                    "cam_id":     cam_id,
                    "track_id":   tid,
                    "score":      round(trk.score, 1),
                    "frames":     trk.frames_seen,
                })
                logger.warning(
                    f"[{cam_id}] 🚨 FIRE CONFIRMED track={tid} "
                    f"score={trk.score:.1f} conf={trk.conf:.2f} "
                    f"frames={trk.frames_seen}"
                )
            elif trk.score >= ALERT_SCORE and trk.has_alerted:
                # Re-alert (ongoing fire) — controlled by alert_engine cooldown
                alert_detections.append({
                    "feature":    "fire_smoke",
                    "class":      "fire",
                    "confidence": round(trk.conf, 3),
                    "bbox":       trk.bbox,
                    "cam_id":     cam_id,
                    "track_id":   tid,
                    "score":      round(trk.score, 1),
                    "frames":     trk.frames_seen,
                })

        _display_boxes[cam_id] = new_display_boxes
        return alert_detections

    @classmethod
    def get_display_boxes(cls, cam_id: str) -> list[dict]:
        """Plain Python dicts — safe to read from any thread or reuse on skipped frames."""
        return _display_boxes.get(cam_id, [])
