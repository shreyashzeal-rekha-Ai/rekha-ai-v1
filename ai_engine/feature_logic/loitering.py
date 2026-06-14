"""
feature_logic/loitering.py
--------------------------
Loitering detector -- Zone Occupancy Timer model + Per-Person ID Dwell Tracking.

WHY THIS APPROACH:
  Individual person tracking (YOLO IDs or centroids) is fundamentally broken
  for loitering because:
    - YOLO loses IDs when a person moves or is briefly occluded
    - Person leaves frame and returns -> brand new ID
    - Centroid tracker fails when person comes back from a different angle

THE FIX -- Track the ZONE, not the person (for the alert clock):
  The zone has a single occupancy clock.
  As long as ANYONE is detected inside -> clock keeps running.
  Only reset clock if zone is completely empty for EMPTY_GRACE_SECONDS.

PER-PERSON ID TRACKING (additive layer):
  On top of the zone clock, we also record WHEN each track_id first entered
  the zone. At alert time, we report exactly which Person IDs have individually
  been inside for >= timeout_seconds.

BUGS FIXED (v3):
  1. Foot-point polygon test  -- use bottom-center (cx, box[3]) instead of
     body center. Feet are stable near edges on blurry DVR feeds; body-center
     jitters across the boundary even for a stationary person. (If camera is
     steeply overhead and feet land outside the polygon, the per-person grace
     window absorbs the single-frame jitter.)
  2. Per-person grace window  -- a brief 1-frame drop-out no longer resets the
     individual dwell clock. Each person entry expires only after
     PERSON_GRACE_SECONDS of absence, mirroring the zone-level grace logic.
  3. Proximity ID-merge       -- when YOLO assigns a new track_id to a person
     already counted (common on blurry DVR), the new id INHERITS the existing
     dwell timer instead of starting fresh. Merger is based on foot-point
     proximity within MERGE_PROXIMITY_PX pixels.
  4. Grace-active count/ids   -- loitering_ids and reported count are derived
     from the grace-active dwell MAP, not from a single frame's ids_inside.
     A person who flickered out on the exact alert frame still counts, and
     the reported count stops bouncing.

BUGS FIXED (v4):
  5. Count/alert accuracy     -- count, loitering_ids, and alert triggers now
     require PHYSICAL presence in zone this frame. Ghost grace-active track IDs
     no longer inflate counts or fire alerts while absent.
  6. Per-zone timeout         -- uses zone.dwell_seconds when set, else camera
     loitering_timeout_seconds.
  7. Per-zone schedule        -- zones outside their schedule window are skipped.
  8. Merge constants          -- proximity/color thresholds use named constants.

BUGS FIXED (v5):
  9. Identity swap detection  -- when the tracker reuses a loiterer's track ID
     for a different person (common when one person leaves and another enters
     the same spot), appearance drift vs the entry baseline resets the dwell
     clock so the newcomer is not falsely alerted.
 10. Post-alert merge guard   -- a grace-active ghost who already triggered a
     loitering alert is no longer merged onto a new track_id after a brief
     absence; the newcomer starts a fresh dwell timer instead.
"""

import math
import time
import logging
import numpy as np
import cv2

from feature_logic.schedule_utils import is_schedule_active

logger = logging.getLogger("feature_logic.loitering")

# ── Tunable constants ────────────────────────────────────────────────────────
# How long the zone must be COMPLETELY empty before we consider the
# loitering session "over" and reset the clock.
EMPTY_GRACE_SECONDS = 60

# Per-person grace: a person's dwell timer survives this many seconds of
# absence (handles occlusion and tracker dropouts).
# Must be long enough so that if person_tracker.py recovers the ID,
# loitering.py still remembers their timer.
PERSON_GRACE_SECONDS = 60

# Proximity radius (in inference/640x360 pixel space) for ID-merge.
# When a NEW track_id appears within this many pixels of a grace-active-but-
# currently-absent person, the new id INHERITS the old dwell timer.
MERGE_PROXIMITY_PX = 80

# Color histogram distance threshold for ID-merge (Bhattacharyya, 0=identical).
MERGE_COLOR_THRESHOLD = 0.55

# Appearance drift above this vs the entry baseline means the tracker reused
# this track_id for a different person — reset their dwell clock.
IDENTITY_SWAP_THRESHOLD = 0.45

# After a loitering alert, do not merge the alerted ghost onto a new track_id
# once they have been absent this many seconds (different person likely entered).
POST_ALERT_MERGE_MAX_ABSENCE = 5

# After a loitering alert, a track_id absent from the zone this long is treated
# as a new entrant when they reappear (even if the tracker reused the same ID).
REENTRY_RESET_MIN_ABSENCE = 30


# ── Per-camera, per-zone occupancy state ────────────────────────────────────
# Key: "cam_id::zone_id"
_occupied_since: dict = {}   # timestamp when zone was FIRST occupied
_last_detected:  dict = {}   # timestamp of most recent detection inside
_last_alert:     dict = {}   # timestamp of last alert fired
_person_count:   dict = {}   # number of people currently inside (for alert message)

# ── Per-person dwell tracking ────────────────────────────────────────────────
# Key: "cam_id::zone_id::track_id"
_person_entered:    dict = {}   # when this track_id FIRST entered this zone (session)
_person_last_seen:  dict = {}   # most recent in-zone detection timestamp
_person_last_pos:   dict = {}   # (foot_x, foot_y) of last in-zone foot point
_person_color_sig:     dict = {}   # (top_hist, bottom_hist) for color matching
_person_baseline_sig:  dict = {}   # appearance at zone entry (for identity-swap detection)
_person_last_alert:    dict = {}   # timestamp of the last alert fired for THIS specific person
_person_left_zone_at:  dict = {}   # when this track_id's foot last left the polygon

def extract_color_signature(frame, box):
    """
    Extracts an HSV color histogram for the top half (shirt/skin) and
    bottom half (pants) of a person's bounding box.
    Returns: (top_hist, bottom_hist)
    """
    if frame is None:
        return None
    x1, y1, x2, y2 = map(int, box)
    h_img, w_img = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w_img, x2), min(h_img, y2)
    
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 10:
        return None
        
    h, w = crop.shape[:2]
    mid = h // 2
    top_half = crop[:mid, :]
    bottom_half = crop[mid:, :]
    
    def get_hist(img):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # 16 bins for Hue, 16 bins for Saturation
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist
        
    return (get_hist(top_half), get_hist(bottom_half))

def compare_color_signatures(sig1, sig2):
    """
    Compares two color signatures using Bhattacharyya distance.
    Returns a score from 0.0 (perfect match) to 1.0 (complete mismatch).
    """
    if sig1 is None or sig2 is None:
        return float('inf')
    
    d_top = cv2.compareHist(sig1[0], sig2[0], cv2.HISTCMP_BHATTACHARYYA)
    d_bottom = cv2.compareHist(sig1[1], sig2[1], cv2.HISTCMP_BHATTACHARYYA)
    
    return (d_top + d_bottom) / 2.0


def _purge_person_state(pkey: str):
    """Remove all per-person tracking state for a zone::track_id key."""
    _person_entered.pop(pkey, None)
    _person_last_seen.pop(pkey, None)
    _person_last_pos.pop(pkey, None)
    _person_color_sig.pop(pkey, None)
    _person_baseline_sig.pop(pkey, None)
    _person_last_alert.pop(pkey, None)
    _person_left_zone_at.pop(pkey, None)


def _reset_person_dwell(pkey: str, now: float, baseline_sig=None):
    """Start a fresh dwell session for this track_id (identity swap or new entrant)."""
    _person_entered[pkey] = now
    _person_last_alert.pop(pkey, None)
    if baseline_sig is not None:
        _person_baseline_sig[pkey] = baseline_sig


class LoiteringDetector:

    @classmethod
    def process(cls, result, cam_id, cam_state, zones, timeout_seconds=120, frame=None):
        detections = []

        if not result or not result.boxes:
            # No detections this frame -> treat zone as potentially empty
            cls._handle_empty_frame(cam_id, zones, time.time())
            return detections

        boxes = result.boxes.xyxy.cpu().numpy()
        h, w  = result.orig_shape
        sx, sy = w / 1280.0, h / 720.0

        # ── Extract track IDs from PersonTracker output ──────────────────────
        # result.boxes.id is assigned by PersonTracker (persistent per-camera IDs).
        raw_ids = result.boxes.id
        if raw_ids is not None:
            track_ids = raw_ids.cpu().numpy().astype(int).tolist()
        else:
            # Fallback: synthetic index IDs so zone logic still works
            track_ids = list(range(len(boxes)))

        loitering_zones = [
            z for z in zones
            if (z.get("alert_on_loitering", False) or z.get("type") == "loitering")
            and is_schedule_active(z.get("schedule"))
        ]
        if not loitering_zones:
            return detections

        now = time.time()

        for zone in loitering_zones:
            polygon = zone.get("polygon", [])
            if len(polygon) < 3:
                continue

            zone_id   = zone.get("id", zone.get("name", "zone"))
            zone_name = zone.get("name", "Area")
            key       = f"{cam_id}::{zone_id}"
            zone_timeout = int(zone.get("dwell_seconds") or timeout_seconds)

            # Scale polygon to inference frame size
            scaled_poly = [[int(pt[0] * sx), int(pt[1] * sy)] for pt in polygon]
            poly_arr    = np.array(scaled_poly, dtype=np.int32)

            # ── FIX #1: Use FOOT point (bottom-center) for polygon test ──────
            # The foot point (horizontal center, bottom edge of box) is stable
            # near zone boundaries on blurry DVR feeds. Body-center jitters
            # across the boundary even for a stationary person, causing
            # false "person left the zone" events.
            # Note: if the camera is steeply overhead and feet land outside the
            # polygon, the PERSON_GRACE_SECONDS window below absorbs single-frame
            # jitter without resetting the dwell clock.
            ids_inside   = []
            boxes_inside = []
            foot_points  = {}  # track_id -> (foot_x, foot_y)
            color_sigs   = {}  # track_id -> color signature

            for i, box in enumerate(boxes):
                foot_x = (box[0] + box[2]) / 2.0   # horizontal center
                foot_y = box[3]                      # bottom of bounding box (feet)
                if cv2.pointPolygonTest(poly_arr, (float(foot_x), float(foot_y)), False) >= 0:
                    tid = track_ids[i]
                    ids_inside.append(tid)
                    boxes_inside.append(box)
                    foot_points[tid] = (foot_x, foot_y)
                    # Extract appearance feature for this person
                    color_sigs[tid] = extract_color_signature(frame, box)

            count_inside = len(ids_inside)

            # ── Collect grace-active persons for this zone ───────────────────
            # "Grace-active" = person_last_seen entry exists AND has not expired.
            # These are persons who were recently in the zone (within PERSON_GRACE_SECONDS).
            all_zone_pkeys = [
                pk for pk in list(_person_last_seen.keys())
                if pk.startswith(f"{key}::")
            ]
            grace_active_pkeys = [
                pk for pk in all_zone_pkeys
                if (now - _person_last_seen.get(pk, 0)) <= PERSON_GRACE_SECONDS
            ]
            # Map grace-active track_ids (absent this frame) for ID-merge lookup
            grace_active_absent_tids = set()
            for pk in grace_active_pkeys:
                tid_str = pk.split("::")[-1]
                try:
                    tid_int = int(tid_str)
                    if tid_int not in ids_inside:
                        grace_active_absent_tids.add(tid_int)
                except ValueError:
                    pass

            # ── FIX #2 + #3: Update per-person entries ───────────────────────
            current_person_keys = set()
            for tid in ids_inside:
                pkey = f"{key}::{tid}"
                current_person_keys.add(pkey)

                sig = color_sigs.get(tid)
                zone_absent_seconds = 0.0
                if pkey in _person_left_zone_at:
                    zone_absent_seconds = now - _person_left_zone_at.pop(pkey)

                if pkey in _person_entered:
                    baseline = _person_baseline_sig.get(pkey)
                    should_reset = False

                    if pkey in _person_last_alert and zone_absent_seconds > POST_ALERT_MERGE_MAX_ABSENCE:
                        if zone_absent_seconds >= REENTRY_RESET_MIN_ABSENCE:
                            should_reset = True
                        elif sig is not None and baseline is not None:
                            drift = compare_color_signatures(sig, baseline)
                            if drift >= IDENTITY_SWAP_THRESHOLD:
                                should_reset = True
                    # Do NOT check appearance drift on every frame while continuously
                    # in-zone — lighting/pose changes over minutes were resetting the
                    # dwell clock and blocking repeat alerts at 60s / 120s / 180s.

                    if should_reset:
                        _reset_person_dwell(
                            pkey, now,
                            baseline_sig=sig if sig is not None else baseline,
                        )
                        logger.info(
                            f"[{cam_id}] Zone '{zone_name}': Person #{tid} "
                            f"dwell timer reset (zone_absent={zone_absent_seconds:.0f}s, "
                            f"re-entry after prior alert)."
                        )
                elif pkey not in _person_entered:
                    # FIX #3: Appearance/Color-based ID Merge
                    # If this is a "new" ID, check if their clothing/skin color matches
                    # someone who was recently lost.
                    inherited = False
                    fp = foot_points.get(tid)
                    
                    if fp is not None and sig is not None and grace_active_absent_tids:
                        best_score     = float("inf")
                        best_ghost_tid = None
                        
                        for ghost_tid in list(grace_active_absent_tids):
                            ghost_pkey = f"{key}::{ghost_tid}"
                            ghost_absent = now - _person_last_seen.get(ghost_pkey, now)

                            # FIX #10: Do not inherit a confirmed loiterer's timer once
                            # they have been gone long enough for someone else to enter.
                            if (
                                ghost_pkey in _person_last_alert
                                and ghost_absent > POST_ALERT_MERGE_MAX_ABSENCE
                            ):
                                logger.debug(
                                    f"[Loitering ReID] Skip merge #{ghost_tid}->#{tid}: "
                                    f"ghost already alerted, absent {ghost_absent:.0f}s"
                                )
                                continue

                            ghost_fp   = _person_last_pos.get(ghost_pkey)
                            ghost_sig  = _person_color_sig.get(ghost_pkey)
                            
                            dist_color = compare_color_signatures(sig, ghost_sig)
                            dist_px = math.sqrt(
                                (fp[0] - ghost_fp[0]) ** 2 +
                                (fp[1] - ghost_fp[1]) ** 2
                            ) if ghost_fp else float("inf")
                            
                            # Log every candidate for debugging
                            logger.debug(f"[Loitering ReID] Candidate merge #{ghost_tid}->#{tid}: color_dist={dist_color:.2f}, px_dist={dist_px:.1f}")

                            # STRICT match condition: BOTH must pass.
                            # We require proximity (very close = same person) AND
                            # color similarity (clothing matches = same person).
                            # Using OR caused wrong people's timers to get merged.
                            is_match = (
                                dist_px <= MERGE_PROXIMITY_PX
                                and dist_color < MERGE_COLOR_THRESHOLD
                            )
                            
                            if is_match and dist_color < best_score:
                                best_score     = dist_color
                                best_ghost_tid = ghost_tid

                        if best_ghost_tid is not None:
                            ghost_pkey = f"{key}::{best_ghost_tid}"
                            # Migrate all dicts from old ghost key -> new active key
                            _person_entered[pkey]   = _person_entered.pop(ghost_pkey, now)
                            _person_last_seen[pkey] = _person_last_seen.pop(ghost_pkey, now)
                            
                            if ghost_pkey in _person_last_alert:
                                _person_last_alert[pkey] = _person_last_alert.pop(ghost_pkey)

                            if ghost_pkey in _person_baseline_sig:
                                _person_baseline_sig[pkey] = _person_baseline_sig.pop(ghost_pkey)
                            elif sig is not None:
                                _person_baseline_sig[pkey] = sig
                                
                            _person_last_pos.pop(ghost_pkey, None)
                            _person_color_sig.pop(ghost_pkey, None)
                            
                            # Mark ghost as consumed
                            grace_active_absent_tids.discard(best_ghost_tid)
                            logger.debug(
                                f"[{cam_id}] Zone '{zone_name}': ID #{best_ghost_tid}"
                                f" → #{tid} (Color merge score={best_score:.2f})"
                            )
                            inherited = True

                    if not inherited:
                        _reset_person_dwell(pkey, now, baseline_sig=sig)
                        logger.debug(
                            f"[{cam_id}] Zone '{zone_name}': Person #{tid} entered."
                        )

                # Always refresh last-seen, pos, and color signature for in-zone persons
                _person_last_seen[pkey] = now
                _person_last_pos[pkey]  = foot_points.get(tid, (0.0, 0.0))
                # Only update signature if we got a valid one (prevents blurring with occlusion)
                if color_sigs.get(tid) is not None:
                    _person_color_sig[pkey] = color_sigs.get(tid)

            # ── FIX #2: Expire stale per-person entries (grace window) ────────
            # OLD logic: deleted any pkey not in current_person_keys (zero grace).
            # NEW logic: only expire after absence > PERSON_GRACE_SECONDS.
            expired_pkeys = [
                pk for pk in all_zone_pkeys
                if pk not in current_person_keys
                and (now - _person_last_seen.get(pk, 0)) > PERSON_GRACE_SECONDS
            ]
            for pk in expired_pkeys:
                _purge_person_state(pk)

            # Mark persons who left the zone polygon this frame
            for pk in all_zone_pkeys:
                if pk not in current_person_keys and pk in _person_entered:
                    if pk not in _person_left_zone_at:
                        _person_left_zone_at[pk] = now

            # ── Prune unmerged ghost IDs when fewer people are in zone ────────
            # YOLO re-assigns IDs on blurry DVR feeds. If merge fails, old ghost
            # entries linger for PERSON_GRACE_SECONDS and inflate internal state.
            # When absent ghosts outnumber in-zone people, drop the oldest ghosts
            # that were not merged this frame.
            if count_inside > 0 and grace_active_absent_tids:
                max_ghosts = max(0, len(grace_active_absent_tids) - count_inside)
                if max_ghosts > 0:
                    ghost_candidates = []
                    for ghost_tid in grace_active_absent_tids:
                        ghost_pkey = f"{key}::{ghost_tid}"
                        ghost_candidates.append(
                            (_person_last_seen.get(ghost_pkey, 0), ghost_pkey)
                        )
                    ghost_candidates.sort()
                    for _, ghost_pkey in ghost_candidates[:max_ghosts]:
                        _purge_person_state(ghost_pkey)
                        logger.debug(
                            f"[{cam_id}] Zone '{zone_name}': purged unmerged ghost {ghost_pkey}"
                        )

            if count_inside > 0:
                # ── Zone is OCCUPIED ─────────────────────────────────────────
                _last_detected[key]  = now
                _person_count[key]   = count_inside

                if key not in _occupied_since:
                    _occupied_since[key] = now
                    logger.debug(
                        f"[{cam_id}] Zone '{zone_name}' occupancy started."
                    )

                dwell_time = int(now - _occupied_since[key])
                logger.debug(
                    f"[{cam_id}] Zone '{zone_name}': {count_inside} person(s) "
                    f"inside {ids_inside}, dwell={dwell_time}s / {zone_timeout}s"
                )

                # ── Per-Person Independent Alerts ────────────────────────────
                # Only persons PHYSICALLY inside the zone this frame can trigger
                # an alert or appear in count/loitering_ids. Grace state is kept
                # for dwell-timer continuity, but absent ghost IDs must not
                # inflate the reported count or fire alerts while out of zone.
                present_pkeys = [
                    f"{key}::{tid}" for tid in ids_inside
                ]

                # Repeat every zone_timeout so a 5-minute dwell repeats every 5 minutes.
                repeat_interval = zone_timeout

                alert_trigger_tids = []
                all_loitering_tids = []

                for pk in present_pkeys:
                    person_dwell = int(now - _person_entered.get(pk, now))
                    if person_dwell < zone_timeout:
                        continue

                    try:
                        tid = int(pk.split("::")[-1])
                    except ValueError:
                        continue

                    all_loitering_tids.append((tid, person_dwell, pk))

                    since_person_alert = now - _person_last_alert.get(pk, 0)
                    if since_person_alert >= repeat_interval:
                        alert_trigger_tids.append((tid, person_dwell, pk))

                # If ANY present person is due for a loitering alert right now
                if alert_trigger_tids:
                    # Sort by dwell time descending (longest loiterer first)
                    all_loitering_tids.sort(key=lambda x: x[1], reverse=True)
                    alert_trigger_tids.sort(key=lambda x: x[1], reverse=True)

                    # Mark the specific people who triggered this alert as having been alerted
                    for tid, person_dwell, pk in alert_trigger_tids:
                        _person_last_alert[pk] = now

                    reported_count = count_inside

                    # Build person ID string from loiterers physically in zone
                    id_parts = []
                    loitering_tids_only = []
                    for tid, pd, pk in all_loitering_tids:
                        loitering_tids_only.append(tid)
                        pm = pd // 60
                        ps = pd % 60
                        pd_str = f"{pm}m {ps}s" if pm > 0 else f"{ps}s"
                        id_parts.append(f"#{tid} ({pd_str})")

                    person_id_str = ", ".join(id_parts)
                    _last_alert[key] = now

                    msg = (
                        f"Loitering Detected in '{zone_name}': "
                        f"{reported_count} person(s) in zone. "
                        f"Loitering: {person_id_str}"
                    )

                    top_tid = alert_trigger_tids[0][0]
                    if top_tid in ids_inside:
                        top_idx  = ids_inside.index(top_tid)
                        alert_box = [int(v) for v in boxes_inside[top_idx]]
                    else:
                        alert_box = [int(v) for v in boxes_inside[0]] if boxes_inside else [0,0,0,0]

                    detections.append({
                        "feature":         "loitering",
                        "class":           "person",
                        "confidence":      1.0,
                        "bbox":            alert_box,
                        "cam_id":          cam_id,
                        "zone_name":       zone_name,
                        "count":           reported_count,
                        "dwell_seconds":   alert_trigger_tids[0][1],
                        "loitering_ids":   loitering_tids_only,
                        "all_ids_in_zone": ids_inside,
                        "message":         msg,
                    })
                    logger.warning(f"[{cam_id}] Loitering: {msg}")

            else:
                # ── Zone is EMPTY this frame ──────────────────────────────────
                if key in _last_detected:
                    empty_for = now - _last_detected[key]
                    if empty_for >= EMPTY_GRACE_SECONDS:
                        # Truly empty -- reset the occupancy session
                        dwell = int(_last_detected[key] - _occupied_since.get(key, now))
                        logger.debug(
                            f"[{cam_id}] Zone '{zone_name}' cleared after "
                            f"{dwell}s dwell (empty for {empty_for:.0f}s)."
                        )
                        cls._clear_zone_session(key)
                    # else: zone emptied recently -- grace period, keep clock running

        return detections

    @classmethod
    def _clear_zone_session(cls, key: str):
        """Reset all state for a zone key after it has been confirmed empty."""
        _occupied_since.pop(key, None)
        _last_detected.pop(key, None)
        _last_alert.pop(key, None)
        _person_count.pop(key, None)
        # Purge all per-person entries belonging to this zone
        for store in (
            _person_entered, _person_last_seen, _person_last_pos,
            _person_color_sig, _person_baseline_sig, _person_last_alert,
            _person_left_zone_at,
        ):
            stale = [pk for pk in list(store.keys()) if pk.startswith(f"{key}::")]
            for pk in stale:
                store.pop(pk, None)

    @classmethod
    def reset_state(cls):
        """Clear all module-level state (for tests)."""
        global _occupied_since, _last_detected, _last_alert, _person_count
        global _person_entered, _person_last_seen, _person_last_pos
        global _person_color_sig, _person_baseline_sig, _person_last_alert
        global _person_left_zone_at
        _occupied_since.clear()
        _last_detected.clear()
        _last_alert.clear()
        _person_count.clear()
        _person_entered.clear()
        _person_last_seen.clear()
        _person_last_pos.clear()
        _person_color_sig.clear()
        _person_baseline_sig.clear()
        _person_last_alert.clear()
        _person_left_zone_at.clear()

    @classmethod
    def _handle_empty_frame(cls, cam_id: str, zones, now: float):
        """Called when YOLO returned zero detections -- check each zone's grace."""
        for zone in zones:
            if not (zone.get("alert_on_loitering", False) or zone.get("type") == "loitering"):
                continue
            zone_id = zone.get("id", zone.get("name", "zone"))
            key = f"{cam_id}::{zone_id}"
            if key in _last_detected:
                empty_for = now - _last_detected[key]
                if empty_for >= EMPTY_GRACE_SECONDS:
                    logger.debug(
                        f"[{cam_id}] Zone '{zone.get('name', zone_id)}' "
                        f"session ended (no detections, grace expired)."
                    )
                    cls._clear_zone_session(key)