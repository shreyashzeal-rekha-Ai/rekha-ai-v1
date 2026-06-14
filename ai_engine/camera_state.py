"""
camera_state.py
---------------
Per-camera tracking state. One instance per camera.
Holds ALL stateful data needed by loitering, footfall,
personal monitoring, and other time-based features.
Reset only on full system restart.
"""

import time
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class TrackRecord:
    """State for one tracked person (one track_id)."""
    track_id:     int
    first_seen:   float = field(default_factory=time.time)
    last_seen:    float = field(default_factory=time.time)
    last_pos:     tuple = (0, 0)          # centroid (cx, cy)
    current_zone: str   = None            # zone id they are currently in
    zone_entry_time: float = None         # when they entered current zone
    crossed_line_ids: set = field(default_factory=set)  # counting lines already crossed
    alert_fired:  dict  = field(default_factory=dict)   # feature → last alert time


class CameraState:
    """
    Tracks all stateful data for one camera across frames.
    Shared by all feature processors for that camera.
    """

    def __init__(self, cam_id: str):
        self.cam_id = cam_id

        # All active tracks: track_id → TrackRecord
        self.tracks: dict[int, TrackRecord] = {}

        # Footfall totals for this session
        self.footfall_total: int = 0
        self.footfall_in:    int = 0
        self.footfall_out:   int = 0

        # Crowd: last reported count
        self.last_crowd_count: int = 0

        # Tombstoned track IDs (seen and gone) — prevent re-counting on footfall
        self._dead_tracks: set[int] = set()

        # Per-feature cooldowns: feature_name → last alert timestamp
        self._feature_cooldowns: dict[str, float] = {}

    # ── Track management ────────────────────────────────────────────

    def update_track(self, track_id: int, cx: float, cy: float) -> TrackRecord:
        """Update or create a track record. Returns the record."""
        if track_id not in self.tracks:
            self.tracks[track_id] = TrackRecord(track_id=track_id)
        rec = self.tracks[track_id]
        rec.last_pos  = (cx, cy)
        rec.last_seen = time.time()
        return rec

    def get_track(self, track_id: int) -> TrackRecord | None:
        return self.tracks.get(track_id)

    def prune_dead_tracks(self, active_ids: set[int], max_age_seconds: float = 5.0):
        """Remove tracks not seen for max_age_seconds."""
        now   = time.time()
        stale = [tid for tid, rec in self.tracks.items()
                 if tid not in active_ids and (now - rec.last_seen) > max_age_seconds]
        for tid in stale:
            self._dead_tracks.add(tid)
            del self.tracks[tid]

    # ── Cooldown helpers ────────────────────────────────────────────

    def is_cooldown_active(self, feature: str, cooldown_s: float = 30.0) -> bool:
        last = self._feature_cooldowns.get(feature, 0)
        return (time.time() - last) < cooldown_s

    def mark_alerted(self, feature: str):
        self._feature_cooldowns[feature] = time.time()

    # ── Stats ───────────────────────────────────────────────────────

    def active_count(self) -> int:
        return len(self.tracks)

    def summary(self) -> dict:
        return {
            "cam_id":        self.cam_id,
            "active_people": self.active_count(),
            "footfall_total": self.footfall_total,
            "footfall_in":    self.footfall_in,
            "footfall_out":   self.footfall_out,
        }
