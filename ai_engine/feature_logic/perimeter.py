"""
feature_logic/perimeter.py
---------------------------
Perimeter Intrusion Detector  (v5 — Production-grade, 9-fix rewrite)

WHAT CHANGED FROM v4
─────────────────────
  Fix 1  (Critical)  — Removed `continue` that suppressed crossing logic when
                        a person was inside the proximity band. Both modes now
                        evaluate independently every frame.

  Fix 2  (Critical)  — Replaced infinite-line cross-product crossing check with
                        a true segment-vs-segment intersection test. Walking past
                        the imaginary extension of the line no longer triggers an
                        alert.

  Fix 3  (Medium)    — Crossing logic is skipped for untracked detections
                        (track_id < 0). They use proximity-only mode, which
                        requires no frame-to-frame memory.

  Fix 4  (Medium)    — `_track_state` (replaces `_prev_sides`) is pruned at the
                        end of every process() call. Departed track IDs move to a
                        ghost pool; expired ghosts are deleted.

  Fix 5  (Low)       — Removed the global `_allowed_cache` singleton. Classes
                        are resolved per-call so each camera uses its own model's
                        class list independently.

  Fix 6  (Critical)  — `_track_state` only inherits state when the track already
                        exists in state or matches a ghost. Brand-new track IDs
                        that appear for the first time never get a stale `prev_side`
                        inherited from a previous flash-detection, eliminating
                        crossing false alarms on track ID reuse.

  Fix 7  (High)      — Added `_crossing_fired` per-track flag. When segment
                        intersection fires a crossing alert in a frame, proximity
                        is suppressed for that same track in that same frame,
                        preventing duplicate events.

  Fix 8  (High)      — Ghost pool now stores foot-position coordinates in addition
                        to the last side value. This makes spatial Re-ID matching
                        possible: a new track ID within GHOST_MAX_PX of a ghost
                        inherits its previous side, preventing false crossing alerts
                        when the tracker reassigns an ID after brief occlusion.

  Fix 9  (Medium)    — Cooldown keys in `cam_state._feature_cooldowns` for
                        departed track IDs are cleaned up at the end of process().
                        This prevents the shared CameraState cooldown dict from
                        accumulating thousands of dead perimeter keys over 24/7
                        operation.

  Bug A  (High)      — Premature Cooldown Wipe fixed. Cooldown keys are now only
                        deleted inside _expire_ghosts() after GHOST_TTL_S seconds,
                        not immediately when a box flickers off-screen. Preserves
                        the 8s/15s cooldowns across 1-2 frame tracker flickers.

  Bug B  (Minor)     — Ghost Cloning fixed. _find_ghost() now pops the matched
                        ghost from the pool immediately, so one ghost can only be
                        inherited by exactly one new track per frame.

PUBLIC API — UNCHANGED:
  PerimeterDetector.process(result, cam_id, cam_state, perimeter_line,
                            frame_w, frame_h) -> list[dict]
"""

import math
import time
import logging

logger = logging.getLogger("feature_logic.perimeter")

# ── Canvas reference (frontend draw space) ──────────────────────────────────
CANVAS_W = 1280
CANVAS_H = 720

# ── Detected class sets ──────────────────────────────────────────────────────
URBAN_ANIMAL_CLASSES = {"dog", "cat", "cow", "bird", "horse", "sheep"}
PERSON_CLASSES       = {"person"}

# ── Alert thresholds ─────────────────────────────────────────────────────────
CROSSING_COOLDOWN_S  = 15    # seconds between crossing alerts for the same track
PROXIMITY_COOLDOWN_S = 8     # seconds between proximity alerts (shorter — re-alerts while near)
PROXIMITY_PX         = 40    # foot-point pixel distance to line = "on the boundary"

# ── Ghost pool Re-ID settings ────────────────────────────────────────────────
GHOST_TTL_S   = 4.0    # seconds to keep a departed track as a matchable ghost
GHOST_MAX_PX  = 80     # max pixel distance to match a returning track to a ghost


# ══════════════════════════════════════════════════════════════════════════════
# Module-level state  (per-camera dicts — one entry per cam_id)
# ══════════════════════════════════════════════════════════════════════════════

# _track_state[cam_id][track_id] = {"side": float, "pos": (foot_x, foot_y)}
_track_state: dict[str, dict[int, dict]] = {}

# _ghost_pool[cam_id][track_id] = {"side": float, "pos": (foot_x, foot_y), "time": float}
_ghost_pool:  dict[str, dict[int, dict]] = {}


# ══════════════════════════════════════════════════════════════════════════════
# Geometry helpers
# ══════════════════════════════════════════════════════════════════════════════

def _scale_line(raw_line, frame_w: int, frame_h: int):
    """Scale a [[x1,y1],[x2,y2]] canvas line to real frame pixel coordinates."""
    sx = frame_w / CANVAS_W
    sy = frame_h / CANVAS_H
    return (raw_line[0][0] * sx, raw_line[0][1] * sy,
            raw_line[1][0] * sx, raw_line[1][1] * sy)


def _side_of_line(px: float, py: float,
                  x1: float, y1: float,
                  x2: float, y2: float) -> float:
    """
    Cross-product sign: positive = one side, negative = the other.
    Used for proximity mode side memory update only (not for crossing detection).
    """
    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)


def _dist_point_to_segment(px: float, py: float,
                            x1: float, y1: float,
                            x2: float, y2: float) -> float:
    """Perpendicular pixel distance from point (px,py) to segment (x1,y1)–(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t  = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    cx = x1 + t * dx
    cy = y1 + t * dy
    return math.hypot(px - cx, py - cy)


def _segments_intersect(ax1: float, ay1: float, ax2: float, ay2: float,
                         bx1: float, by1: float, bx2: float, by2: float) -> bool:
    """
    Fix 2 — True segment intersection test.

    Returns True if segment A (movement path) crosses segment B (perimeter line).
    Uses the standard orientation / cross-product method — works for all cases
    including collinear segments.

    Unlike the old infinite-line cross-product, this only triggers when the
    person's movement path actually crosses the DRAWN segment, not its extension.
    """
    def _cross(ox, oy, ax, ay, bx, by) -> float:
        return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)

    def _on_segment(px, py, ax, ay, bx, by) -> bool:
        return (min(ax, bx) <= px <= max(ax, bx) and
                min(ay, by) <= py <= max(ay, by))

    d1 = _cross(bx1, by1, bx2, by2, ax1, ay1)
    d2 = _cross(bx1, by1, bx2, by2, ax2, ay2)
    d3 = _cross(ax1, ay1, ax2, ay2, bx1, by1)
    d4 = _cross(ax1, ay1, ax2, ay2, bx2, by2)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True

    # Collinear edge cases
    if d1 == 0 and _on_segment(ax1, ay1, bx1, by1, bx2, by2): return True
    if d2 == 0 and _on_segment(ax2, ay2, bx1, by1, bx2, by2): return True
    if d3 == 0 and _on_segment(bx1, by1, ax1, ay1, ax2, ay2): return True
    if d4 == 0 and _on_segment(bx2, by2, ax1, ay1, ax2, ay2): return True

    return False


# ══════════════════════════════════════════════════════════════════════════════
# Class resolution  (Fix 5 — no global cache)
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_allowed_classes(names: dict) -> set:
    """
    Resolve the set of class names this perimeter detector cares about.
    Called per-frame — no global singleton. Each camera's model is evaluated
    independently, so a person-only camera and a multi-class camera never
    contaminate each other's class set.
    """
    model_lower = {v.lower() for v in names.values()}
    animals     = URBAN_ANIMAL_CLASSES & model_lower
    allowed     = set(PERSON_CLASSES)
    if animals:
        allowed |= animals
    return allowed


# ══════════════════════════════════════════════════════════════════════════════
# Ghost pool helpers  (Fix 8 — spatial Re-ID)
# ══════════════════════════════════════════════════════════════════════════════

def _find_ghost(cam_id: str, foot_x: float, foot_y: float) -> dict | None:
    """
    Search the ghost pool for a departed track whose last known foot-position
    is within GHOST_MAX_PX of (foot_x, foot_y).  Returns the ghost dict if
    found, else None.  Picks the spatially nearest ghost when multiple qualify.

    Bug fix (Ghost Cloning): The matched ghost is immediately REMOVED from the
    pool so that a second new track appearing in the same frame at a nearby
    position cannot inherit the same ghost state.  One ghost → one new track.
    """
    ghosts   = _ghost_pool.get(cam_id, {})
    best_d   = GHOST_MAX_PX
    best_tid = None
    best_g   = None
    for tid, g in ghosts.items():
        gx, gy = g["pos"]
        d = math.hypot(foot_x - gx, foot_y - gy)
        if d < best_d:
            best_d   = d
            best_tid = tid
            best_g   = g
    if best_tid is not None:
        # Pop the ghost so no other track can claim it this frame
        del ghosts[best_tid]
    return best_g


def _expire_ghosts(cam_id: str, now: float, cam_state, departed_tids: set):
    """
    Expire ghosts that have exceeded the Re-ID window (GHOST_TTL_S).

    Bug fix (Premature Cooldown Wipe): Cooldown keys in cam_state are ONLY
    cleaned here — after the ghost has truly expired — NOT when the track first
    disappears from a frame.  This preserves the 8-second / 15-second cooldowns
    across the 1–2 frame box-flicker that AI trackers commonly produce, which
    would otherwise cause immediate re-alerting on flicker re-acquisition.

    Args:
        cam_id:        Camera identifier.
        now:           Current timestamp (time.time()).
        cam_state:     CameraState for this camera (used for cooldown cleanup).
        departed_tids: IDs that moved to the ghost pool this frame — these are
                       candidates whose ghosts may have already expired instantly
                       if GHOST_TTL_S is very short.  Passed for completeness;
                       expiry logic uses the stored timestamp, not this set.
    """
    ghosts  = _ghost_pool.get(cam_id, {})
    expired = [tid for tid, g in ghosts.items() if now - g["time"] > GHOST_TTL_S]
    for tid in expired:
        del ghosts[tid]
        # Safe to wipe cooldown now — person has been gone for GHOST_TTL_S seconds
        cam_state._feature_cooldowns.pop(f"perimeter_prox_{cam_id}_{tid}", None)
        cam_state._feature_cooldowns.pop(f"perimeter_cross_{cam_id}_{tid}", None)
        logger.debug(
            f"[{cam_id}] ghost expired: track={tid} — cooldown keys cleared"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Event builder
# ══════════════════════════════════════════════════════════════════════════════

def _make_event(cam_id: str, cls_name: str, alert_type: str, conf: float,
                xyxy: list, track_id: int, mode: str, dist: float | None) -> dict:
    """Build the standardised alert event dict."""
    if mode == "proximity":
        msg = (
            f"{'Animal' if alert_type == 'animal' else 'Person'} on perimeter line | "
            f"{cls_name.capitalize()} (track #{track_id}, {dist:.0f}px from line)"
        )
    else:
        msg = (
            f"{'Animal' if alert_type == 'animal' else 'Person'} crossed perimeter | "
            f"{cls_name.capitalize()} (track #{track_id})"
        )
    return {
        "feature":    "perimeter",
        "class":      cls_name,
        "alert_type": alert_type,
        "mode":       mode,
        "confidence": round(conf, 3),
        "bbox":       [int(v) for v in xyxy],
        "cam_id":     cam_id,
        "track_id":   track_id,
        "message":    msg,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PerimeterDetector  (v5)
# ══════════════════════════════════════════════════════════════════════════════

class PerimeterDetector:
    """
    Perimeter Intrusion Detector v5.

    Dual-mode detection — segment intersection (crossing) + proximity — with
    ghost-pool Re-ID, bounded memory, and per-camera class resolution.
    Public API is identical to v4; no changes required in main.py.
    """

    @staticmethod
    def process(
        result,
        cam_id:         str,
        cam_state,
        perimeter_line: list,
        frame_w:        int = CANVAS_W,
        frame_h:        int = CANVAS_H,
    ) -> list:
        """
        Process one inference frame for one camera.

        Args:
            result:          PersonTracker result (ultralytics Results-compatible).
            cam_id:          Camera identifier string (e.g. "cam_01").
            cam_state:       CameraState instance for this camera (cooldown tracking).
            perimeter_line:  [[x1,y1],[x2,y2]] in 1280×720 canvas coordinates.
            frame_w/frame_h: Actual inference frame dimensions (default 640×360).

        Returns:
            List of alert event dicts (may be empty).
        """

        # ── Guard: need detections ───────────────────────────────────────────
        if result is None or result.boxes is None:
            return []
        if not perimeter_line or len(perimeter_line) < 2:
            logger.warning(f"[{cam_id}] Perimeter line not configured.")
            return []

        # ── Scale canvas coordinates → real frame pixels ─────────────────────
        lx1, ly1, lx2, ly2 = _scale_line(perimeter_line, frame_w, frame_h)

        # ── Fix 5: per-call class resolution (no global cache) ───────────────
        names   = result.names or {}
        allowed = _resolve_allowed_classes(names)

        boxes     = result.boxes
        track_ids = boxes.id
        events    = []
        now       = time.time()

        # ── Ensure per-camera state dicts exist ──────────────────────────────
        if cam_id not in _track_state:
            _track_state[cam_id] = {}
        if cam_id not in _ghost_pool:
            _ghost_pool[cam_id]  = {}

        cam_tracks = _track_state[cam_id]

        # Track all IDs seen this frame for end-of-loop pruning
        active_ids: set[int] = set()

        # Fix 7: per-frame set of tracks that already fired a crossing alert
        #        → suppresses same-frame duplicate proximity event
        crossing_fired_ids: set[int] = set()

        # ── Main detection loop ───────────────────────────────────────────────
        for i in range(len(boxes)):

            # ── Class filter ─────────────────────────────────────────────────
            cls_id   = int(boxes.cls[i].item())
            cls_name = names.get(cls_id, "unknown").lower()
            if cls_name not in allowed:
                continue

            conf     = float(boxes.conf[i].item())
            xyxy     = boxes.xyxy[i].tolist()
            track_id = int(track_ids[i].item()) if track_ids is not None else -(i + 1)

            # Foot-point = bottom-centre of bounding box
            foot_x = (xyxy[0] + xyxy[2]) / 2.0
            foot_y =  xyxy[3]

            is_animal  = cls_name in URBAN_ANIMAL_CLASSES
            alert_type = "animal" if is_animal else "person"

            # Track this ID as active this frame
            if track_id >= 0:
                active_ids.add(track_id)

            logger.debug(
                f"[{cam_id}] track={track_id} cls={cls_name} "
                f"foot=({foot_x:.0f},{foot_y:.0f})"
            )

            # ── Retrieve / Re-ID previous state ──────────────────────────────
            # Fix 6+8: Only inherit state from a direct match or a ghost pool
            #          spatial match.  Brand-new tracks with no history never get
            #          a stale prev_side accidentally.
            prev_state = cam_tracks.get(track_id)

            if prev_state is None and track_id >= 0:
                ghost = _find_ghost(cam_id, foot_x, foot_y)
                if ghost:
                    # Inherit the ghost's last known side so the crossing
                    # sign-flip is evaluated relative to their actual last
                    # position, not a stale unrelated entry.
                    prev_state = ghost
                    logger.debug(
                        f"[{cam_id}] track={track_id} Re-ID ghost → "
                        f"inherited side={ghost['side']:+.0f} "
                        f"pos=({ghost['pos'][0]:.0f},{ghost['pos'][1]:.0f})"
                    )

            # Current side value (used for state update only — NOT for crossing)
            current_side = _side_of_line(foot_x, foot_y, lx1, ly1, lx2, ly2)

            # ── Mode A: SEGMENT INTERSECTION — Crossing Detection ─────────────
            # Fix 1: No `continue` — both modes evaluated independently.
            # Fix 2: Uses segment intersection, not infinite-line sign-change.
            # Fix 3: Skip for untracked detections (track_id < 0).
            if track_id >= 0 and prev_state is not None:
                prev_x, prev_y = prev_state["pos"]

                if _segments_intersect(
                    prev_x, prev_y, foot_x, foot_y,   # movement path
                    lx1,   ly1,    lx2,    ly2         # perimeter segment
                ):
                    cross_key = f"perimeter_cross_{cam_id}_{track_id}"
                    if not cam_state.is_cooldown_active(cross_key, CROSSING_COOLDOWN_S):
                        cam_state.mark_alerted(cross_key)
                        events.append(_make_event(
                            cam_id, cls_name, alert_type, conf, xyxy,
                            track_id, "crossing", None
                        ))
                        crossing_fired_ids.add(track_id)
                        logger.warning(
                            f"[{cam_id}] PERIMETER [crossing] {cls_name} "
                            f"track={track_id} "
                            f"path=({prev_x:.0f},{prev_y:.0f})"
                            f"→({foot_x:.0f},{foot_y:.0f})"
                        )

            # ── Mode B: PROXIMITY — foot-point within PROXIMITY_PX of line ────
            # Fix 1: No longer suppressed — runs every frame.
            # Fix 7: Suppressed if a crossing already fired this frame (same track).
            dist = _dist_point_to_segment(foot_x, foot_y, lx1, ly1, lx2, ly2)
            logger.debug(
                f"[{cam_id}] track={track_id} "
                f"dist_to_line={dist:.1f}px threshold={PROXIMITY_PX}px"
            )

            if dist <= PROXIMITY_PX and track_id not in crossing_fired_ids:
                prox_key = f"perimeter_prox_{cam_id}_{track_id}"
                if not cam_state.is_cooldown_active(prox_key, PROXIMITY_COOLDOWN_S):
                    cam_state.mark_alerted(prox_key)
                    events.append(_make_event(
                        cam_id, cls_name, alert_type, conf, xyxy,
                        track_id, "proximity", dist
                    ))
                    logger.warning(
                        f"[{cam_id}] PERIMETER [proximity] {cls_name} "
                        f"track={track_id} dist={dist:.0f}px"
                    )

            # ── Update track state ────────────────────────────────────────────
            if track_id >= 0:
                cam_tracks[track_id] = {
                    "side": current_side,
                    "pos":  (foot_x, foot_y),
                }

        # ── End-of-frame: prune departed tracks → ghost pool  (Fix 4, 8, 9) ──
        departed_ids = set(cam_tracks.keys()) - active_ids
        for tid in departed_ids:
            departed_state = cam_tracks.pop(tid)
            # Move to ghost pool so returning tracks can Re-ID spatially
            _ghost_pool[cam_id][tid] = {
                "side": departed_state["side"],
                "pos":  departed_state["pos"],
                "time": now,
            }

        # Fix 4 + 9 (with flicker-safe cooldown cleanup):
        # Expire ghosts that outlived GHOST_TTL_S.  Cooldown keys are wiped
        # INSIDE _expire_ghosts — only after the ghost truly expires — so a
        # 1-2 frame bounding-box flicker does NOT reset the alert cooldown.
        _expire_ghosts(cam_id, now, cam_state, departed_ids)

        logger.debug(
            f"[{cam_id}] perimeter state: "
            f"active={len(cam_tracks)} ghosts={len(_ghost_pool.get(cam_id, {}))}"
        )

        return events  