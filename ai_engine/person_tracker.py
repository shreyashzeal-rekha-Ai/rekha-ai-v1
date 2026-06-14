"""
ai_engine/person_tracker.py
----------------------------
Implements temporal smoothing, track persistence, and IoU/centroid-based
re-association.  Works in two modes:

  • With .predict()  [current default] — YOLO boxes have no .id.
    All association is done by IoU matching + centroid-distance fallback.

  • With .track()    [legacy]         — YOLO ByteTrack IDs are used for fast
    lookup; IoU is the fallback.  Backward-compatible; no code change needed
    to switch back.

Mocks the Ultralytics Results object interface for seamless downstream
compatibility.

BLURRY DVR IMPROVEMENT — Proximity-based ghost recovery:
  When a track is deleted (person disappeared) and a new detection appears
  within PROXIMITY_PX pixels of the last known position within
  GHOST_WINDOW_SECONDS, the old track ID is REUSED instead of creating a
  new one.  This means loitering dwell timers never reset due to brief
  occlusions or ID switches caused by DVR blur.
"""

import os
import math
import time
import torch
import numpy as np

# ── Proximity-based ghost recovery tunables ──────────────────────────────────
# If a new detection appears within this many pixels of a recently-lost track's
# last position, reuse the old track ID (blurry DVR ID-switch recovery).
PROXIMITY_PX = 80       # pixels — increase if camera resolution is very low

# How long (seconds) a "ghost" (deleted track) is remembered for recovery.
GHOST_WINDOW_SECONDS = 8.0   # 8 s covers typical DVR occlusion gaps


# ── Geometry helpers ────────────────────────────────────────────────────────

def get_iou(box1, box2):
    """Intersection-over-Union of two [x1,y1,x2,y2] boxes."""
    xi1 = max(box1[0], box2[0])
    yi1 = max(box1[1], box2[1])
    xi2 = min(box1[2], box2[2])
    yi2 = min(box1[3], box2[3])
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    a1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    a2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


def centroid_distance(box1, box2):
    """Euclidean distance between box centres (pixels)."""
    cx1 = (box1[0] + box1[2]) / 2
    cy1 = (box1[1] + box1[3]) / 2
    cx2 = (box2[0] + box2[2]) / 2
    cy2 = (box2[1] + box2[3]) / 2
    return math.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)


def box_diagonal(box):
    """Diagonal length of a box — used to normalise centroid distance."""
    w = box[2] - box[0]
    h = box[3] - box[1]
    return math.sqrt(w * w + h * h) if (w > 0 and h > 0) else 1.0


# ── Ultralytics interface mocks ─────────────────────────────────────────────

class CustomTrackedBoxes:
    """Mocks the ultralytics.engine.results.Boxes interface."""

    def __init__(self, xyxy_list, id_list, conf_list, cls_list, device="cpu"):
        self.device = device
        self.xyxy = (
            torch.tensor(xyxy_list, dtype=torch.float32, device=device)
            if xyxy_list
            else torch.empty((0, 4), dtype=torch.float32, device=device)
        )
        self.id = (
            torch.tensor(id_list, dtype=torch.int32, device=device)
            if id_list
            else None
        )
        self.conf = (
            torch.tensor(conf_list, dtype=torch.float32, device=device)
            if conf_list
            else torch.empty((0,), dtype=torch.float32, device=device)
        )
        self.cls = (
            torch.tensor(cls_list, dtype=torch.int32, device=device)
            if cls_list
            else torch.empty((0,), dtype=torch.int32, device=device)
        )

    def __len__(self):
        return self.xyxy.shape[0]


class CustomTrackedResults:
    """Mocks the ultralytics.engine.results.Results interface."""

    def __init__(self, boxes, names, orig_shape=(360, 640)):
        self.boxes = boxes
        self.names = names
        self.orig_shape = orig_shape


# ── PersonTracker ────────────────────────────────────────────────────────────

class PersonTracker:
    """
    Per-camera tracker.  Each CameraProcessor owns ONE instance.

    Parameters
    ----------
    max_missed_frames : int
        Frames of inference with no match before a track is deleted.
        At every-3rd-frame inference (≈10 fps), 45 = ≈4.5 s.
    alpha : float
        EMA blend factor for box smoothing.  Lower = smoother but slower.
    min_frames_to_verify : int
        A track must be seen this many times before it is drawn/used.
        Prevents flash-detections from triggering alerts.
    iou_threshold : float
        Minimum IoU to re-associate a detection with an existing track.
        Lowered to 0.35 (was 0.45) so that persons moving between
        every-3rd-frame inferences still match even with larger displacement.
    centroid_max_ratio : float
        Fallback: if IoU == 0 but the detection centre is within
        (centroid_max_ratio × box_diagonal) pixels of a track, still match.
        Handles fast-moving persons whose boxes no longer overlap.
    max_draw_missed : int
        Track is shown in annotations up to this many missed frames.
    """

    def __init__(
        self,
        max_missed_frames: int = 45,
        alpha: float = 0.3,
        min_frames_to_verify: int = 2,
        iou_threshold: float = 0.35,
        centroid_max_ratio: float = 0.6,
        max_draw_missed: int = 2,
    ):
        self.max_missed        = max_missed_frames
        self.alpha             = alpha
        self.min_frames_to_verify = min_frames_to_verify
        self.iou_threshold     = iou_threshold
        self.centroid_max_ratio = centroid_max_ratio
        self.max_draw_missed   = max_draw_missed

        # tracks: {track_id: {box, conf, cls, missed, seen_count}}
        self.tracks: dict[int, dict] = {}
        self._next_id = 1

        # Optional YOLO→persistent ID map (used only when .track() returns IDs)
        self.yolo_to_persist: dict[int, int] = {}

        # Ghost recovery: remembers the last known position + timestamp of
        # recently-deleted tracks so proximity matching can reuse their IDs.
        # {track_id: {"cx": float, "cy": float, "ts": float}}
        self._ghost_positions: dict[int, dict] = {}

    # ── internal helpers ────────────────────────────────────────────────

    def _new_id(self) -> int:
        tid = self._next_id
        self._next_id += 1
        return tid

    def _ema(self, new_val, old_val):
        """Exponential Moving Average blend."""
        return [
            self.alpha * n + (1.0 - self.alpha) * o
            for n, o in zip(new_val, old_val)
        ]

    def _suppress_duplicates(self, detections, iou_thr=0.72, nest_thr=0.75, min_sep_px=45):
        """
        NMS-style suppression of overlapping / nested boxes.
        Keeps the highest-confidence box when two boxes overlap heavily AND
        their centres are close (same-person double detection).  Two people
        standing side-by-side often have moderate IoU but separated centres —
        those must NOT be merged into one track.
        """
        if not detections:
            return []
        sorted_dets = sorted(detections, key=lambda d: d["conf"], reverse=True)
        kept = []
        for det in sorted_dets:
            box = det["box"]
            overlap = False
            for k in kept:
                kb = k["box"]
                iou = get_iou(box, kb)
                if iou > iou_thr and centroid_distance(box, kb) < min_sep_px:
                    overlap = True
                    break
                # Nesting check: is the smaller box almost entirely inside the larger?
                xi1 = max(box[0], kb[0])
                yi1 = max(box[1], kb[1])
                xi2 = min(box[2], kb[2])
                yi2 = min(box[3], kb[3])
                inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
                if inter > 0:
                    a1 = (box[2]  - box[0])  * (box[3]  - box[1])
                    a2 = (kb[2]   - kb[0])   * (kb[3]   - kb[1])
                    if min(a1, a2) > 0 and inter / min(a1, a2) > nest_thr:
                        overlap = True
                        break
            if not overlap:
                kept.append(det)
        return kept

    def _best_match(self, det_box, candidate_tids, matched):
        """
        Two-pass matching:
          Pass 1 — highest IoU ≥ iou_threshold.
          Pass 2 — centroid within centroid_max_ratio × diagonal (IoU fallback).
        Returns (best_tid, score) or (None, 0).
        """
        best_iou = 0.0
        best_tid = None

        for tid in candidate_tids:
            if tid in matched:
                continue
            t_box = self.tracks[tid]["box"]
            iou = get_iou(det_box, t_box)
            if iou > best_iou:
                best_iou = iou
                best_tid = tid

        if best_iou >= self.iou_threshold:
            return best_tid, best_iou

        # Centroid-distance fallback (catches fast-moving persons)
        best_dist_ratio = float("inf")
        best_tid_c = None
        for tid in candidate_tids:
            if tid in matched:
                continue
            t_box = self.tracks[tid]["box"]
            dist  = centroid_distance(det_box, t_box)
            diag  = box_diagonal(t_box)
            ratio = dist / diag
            if ratio < best_dist_ratio:
                best_dist_ratio = ratio
                best_tid_c = tid

        if best_dist_ratio <= self.centroid_max_ratio and best_tid_c is not None:
            return best_tid_c, best_dist_ratio  # score is ratio here (just for info)

        return None, 0.0

    # ── public API ──────────────────────────────────────────────────────

    def update(self, person_res, is_inference_frame: bool, device: str = "cpu"):
        """
        Call every frame.

        Parameters
        ----------
        person_res : YOLO Results or None
            Raw output from model.predict() / model.track().
            .boxes.id may be None (predict mode) or set (track mode).
        is_inference_frame : bool
            True  → YOLO was run this frame; update track states.
            False → frame was skipped; just return smoothed boxes.
        device : str
            Torch device for output tensors.
        """

        if is_inference_frame:
            # ── 1. Extract YOLO detections ──────────────────────────────
            conf_thresh = float(os.getenv("PERSON_CONFIDENCE", "0.25"))
            raw_detections = []

            if person_res is not None and person_res.boxes is not None:
                boxes     = person_res.boxes
                ids       = boxes.id
                # ids is None when using .predict() — handled gracefully
                track_ids = (
                    ids.cpu().numpy().astype(int)
                    if ids is not None
                    else [None] * len(boxes)
                )
                xyxy  = boxes.xyxy.cpu().numpy().tolist()
                confs = boxes.conf.cpu().numpy().tolist()
                clss  = boxes.cls.cpu().numpy().astype(int).tolist()

                for i in range(len(boxes)):
                    if confs[i] >= conf_thresh:
                        raw_detections.append({
                            "box":      xyxy[i],
                            "conf":     confs[i],
                            "cls":      clss[i],
                            "yolo_tid": track_ids[i],  # None in predict mode
                        })

            # Duplicate / overlap suppression
            raw_detections = self._suppress_duplicates(raw_detections)

            # ── 2. Fast-path: match via YOLO track IDs (track() mode only) ──
            matched = set()
            unmatched_raw = []

            for det in raw_detections:
                ytid      = det["yolo_tid"]
                persist_id = None

                if ytid is not None:
                    # Direct map lookup
                    if ytid in self.yolo_to_persist and self.yolo_to_persist[ytid] in self.tracks:
                        persist_id = self.yolo_to_persist[ytid]
                    # Or direct track match
                    elif ytid in self.tracks:
                        persist_id = ytid
                        self.yolo_to_persist[ytid] = ytid

                if persist_id is not None and persist_id not in matched:
                    trk = self.tracks[persist_id]
                    trk["box"]        = self._ema(det["box"], trk["box"])
                    trk["conf"]       = self.alpha * det["conf"] + (1 - self.alpha) * trk["conf"]
                    trk["missed"]     = 0
                    trk["seen_count"] += 1
                    matched.add(persist_id)
                else:
                    unmatched_raw.append(det)

            # ── 3. IoU + centroid matching for the rest ─────────────────
            candidates = [tid for tid in self.tracks if tid not in matched]

            for det in unmatched_raw:
                best_tid, _ = self._best_match(det["box"], candidates, matched)

                if best_tid is not None:
                    trk = self.tracks[best_tid]
                    trk["box"]        = self._ema(det["box"], trk["box"])
                    trk["conf"]       = self.alpha * det["conf"] + (1 - self.alpha) * trk["conf"]
                    trk["missed"]     = 0
                    trk["seen_count"] += 1
                    matched.add(best_tid)
                    candidates.remove(best_tid)
                    if det["yolo_tid"] is not None:
                        self.yolo_to_persist[det["yolo_tid"]] = best_tid
                else:
                    # ── Proximity ghost recovery (blurry DVR ID-switch fix) ──
                    # Before assigning a brand-new ID, check if this detection
                    # is close to a recently-lost track. If yes, REUSE that ID
                    # so loitering timers (keyed by track_id) don't reset.
                    det_cx = (det["box"][0] + det["box"][2]) / 2.0
                    det_cy = (det["box"][1] + det["box"][3]) / 2.0

                    recovered_tid = None
                    best_prox = float("inf")
                    for ghost_tid, ghost in self._ghost_positions.items():
                        dist = math.sqrt(
                            (det_cx - ghost["cx"]) ** 2 +
                            (det_cy - ghost["cy"]) ** 2
                        )
                        if dist < PROXIMITY_PX and dist < best_prox:
                            best_prox = dist
                            recovered_tid = ghost_tid

                    if recovered_tid is not None:
                        # Reuse the old track ID — loitering timer continues ✅
                        del self._ghost_positions[recovered_tid]
                        new_tid = recovered_tid
                    else:
                        new_tid = self._new_id()

                    self.tracks[new_tid] = {
                        "box":        det["box"],
                        "conf":       det["conf"],
                        "cls":        det["cls"],
                        "missed":     0,
                        "seen_count": 1,
                    }
                    matched.add(new_tid)
                    if det["yolo_tid"] is not None:
                        self.yolo_to_persist[det["yolo_tid"]] = new_tid

            # ── 4. Age-out unmatched tracks ─────────────────────────────
            for tid in list(self.tracks.keys()):
                if tid not in matched:
                    self.tracks[tid]["missed"] += 1
                    self.tracks[tid]["conf"]   *= 0.95   # decay confidence
                    if self.tracks[tid]["missed"] > self.max_missed:
                        # Save last known centroid as a "ghost" for proximity recovery
                        box = self.tracks[tid]["box"]
                        self._ghost_positions[tid] = {
                            "cx": (box[0] + box[2]) / 2.0,
                            "cy": (box[1] + box[3]) / 2.0,
                            "ts": time.time(),
                        }
                        del self.tracks[tid]
                        self.yolo_to_persist = {
                            y: p for y, p in self.yolo_to_persist.items() if p != tid
                        }

            # ── 4b. Expire old ghosts outside the recovery window ───────
            now_ts = time.time()
            self._ghost_positions = {
                tid: ghost
                for tid, ghost in self._ghost_positions.items()
                if now_ts - ghost["ts"] <= GHOST_WINDOW_SECONDS
            }

        # ── 5. Build output (inference + skipped frames) ────────────────
        xyxy_list, id_list, conf_list, cls_list = [], [], [], []

        for tid, trk in self.tracks.items():
            if (
                trk["seen_count"] >= self.min_frames_to_verify
                and trk["missed"] <= self.max_draw_missed
            ):
                xyxy_list.append(trk["box"])
                id_list.append(tid)
                conf_list.append(trk["conf"])
                cls_list.append(trk["cls"])

        boxes      = CustomTrackedBoxes(xyxy_list, id_list, conf_list, cls_list, device=device)
        orig_shape = person_res.orig_shape if person_res is not None else (360, 640)
        names      = person_res.names      if person_res is not None else {0: "person"}
        return CustomTrackedResults(boxes, names, orig_shape)
