"""
Accuracy tests for loitering detection.

Verifies that count, loitering_ids, and all_ids_in_zone stay consistent
and that ghost track IDs cannot inflate alerts.
"""

import sys
import time
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, ".")

from feature_logic.loitering import (
    LoiteringDetector,
    _person_entered,
    _person_last_seen,
    _person_last_alert,
    _person_left_zone_at,
    PERSON_GRACE_SECONDS,
    REENTRY_RESET_MIN_ABSENCE,
)


class _FakeBoxes:
    def __init__(self, xyxy_list, track_ids):
        self.xyxy = _FakeTensor(np.array(xyxy_list, dtype=np.float32))
        self.id = _FakeTensor(np.array(track_ids, dtype=np.float32)) if track_ids else None


class _FakeTensor:
    def __init__(self, arr):
        self._arr = arr

    def cpu(self):
        return self

    def numpy(self):
        return self._arr


class _FakeResult:
    def __init__(self, boxes_xyxy, track_ids, orig_shape=(360, 640)):
        self.boxes = _FakeBoxes(boxes_xyxy, track_ids)
        self.orig_shape = orig_shape


# Zone covering the full 640x360 inference frame
FULL_ZONE = {
    "id": "zone_test",
    "name": "Test Zone",
    "type": "loitering",
    "alert_on_loitering": True,
    "polygon": [[0, 0], [1280, 0], [1280, 720], [0, 720]],
    "dwell_seconds": 60,
}


def _box(cx=320, cy=300, w=40, h=80):
    return [cx - w / 2, cy - h, cx + w / 2, cy]


class LoiteringAccuracyTests(unittest.TestCase):

    def setUp(self):
        LoiteringDetector.reset_state()

    def _process(self, boxes, ids, timeout=60, zones=None):
        result = _FakeResult(boxes, ids)
        return LoiteringDetector.process(
            result,
            cam_id="cam_test",
            cam_state=None,
            zones=zones or [FULL_ZONE],
            timeout_seconds=timeout,
            frame=None,
        )

    def test_count_matches_ids_in_zone(self):
        """count must always equal len(all_ids_in_zone)."""
        with patch("feature_logic.loitering.time.time", return_value=1000.0):
            self._process([_box()], [79])

        t_alert = 1000.0 + 61
        with patch("feature_logic.loitering.time.time", return_value=t_alert):
            dets = self._process([_box()], [79])

        self.assertEqual(len(dets), 1)
        det = dets[0]
        self.assertEqual(det["count"], len(det["all_ids_in_zone"]))
        self.assertIn(79, det["loitering_ids"])
        self.assertEqual(det["all_ids_in_zone"], [79])

    def test_ghost_ids_do_not_inflate_count(self):
        """Absent grace-active ghost IDs must not appear in count or loitering_ids."""
        key = "cam_test::zone_test"

        # Simulate 3 ghost persons who left the zone but are grace-active
        for tid, entered_at in [(77, 900.0), (78, 900.0), (81, 910.0)]:
            pk = f"{key}::{tid}"
            _person_entered[pk] = entered_at
            _person_last_seen[pk] = 950.0

        # Person #79 is physically in zone and has exceeded timeout
        pk79 = f"{key}::79"
        _person_entered[pk79] = 900.0
        _person_last_seen[pk79] = 1000.0

        t_now = 1000.0
        with patch("feature_logic.loitering.time.time", return_value=t_now):
            dets = self._process([_box()], [79])

        self.assertEqual(len(dets), 1)
        det = dets[0]
        self.assertEqual(det["count"], 1)
        self.assertEqual(det["all_ids_in_zone"], [79])
        self.assertEqual(det["loitering_ids"], [79])
        self.assertNotIn(77, det["loitering_ids"])
        self.assertNotIn(78, det["loitering_ids"])
        self.assertNotIn(81, det["loitering_ids"])

    def test_no_alert_when_person_absent_despite_grace(self):
        """Person past timeout but absent this frame must NOT fire alert."""
        key = "cam_test::zone_test"
        pk = f"{key}::79"
        _person_entered[pk] = 900.0
        _person_last_seen[pk] = 950.0  # within PERSON_GRACE_SECONDS

        t_now = 1000.0
        with patch("feature_logic.loitering.time.time", return_value=t_now):
            dets = self._process([], [])  # nobody in zone

        self.assertEqual(dets, [])

    def test_alert_only_after_zone_timeout(self):
        """No alert before dwell_seconds threshold."""
        with patch("feature_logic.loitering.time.time", return_value=1000.0):
            self._process([_box()], [79])

        with patch("feature_logic.loitering.time.time", return_value=1050.0):
            dets = self._process([_box()], [79])

        self.assertEqual(dets, [])

    def test_per_zone_timeout_used(self):
        """Zone dwell_seconds overrides camera-level timeout."""
        zone = dict(FULL_ZONE)
        zone["dwell_seconds"] = 30

        with patch("feature_logic.loitering.time.time", return_value=1000.0):
            LoiteringDetector.process(
                _FakeResult([_box()], [79]),
                "cam_test", None, [zone], timeout_seconds=120, frame=None,
            )

        with patch("feature_logic.loitering.time.time", return_value=1031.0):
            dets = LoiteringDetector.process(
                _FakeResult([_box()], [79]),
                "cam_test", None, [zone], timeout_seconds=120, frame=None,
            )

        self.assertEqual(len(dets), 1)

    def test_off_schedule_zone_skipped(self):
        """Zones with inactive schedule must not produce alerts."""
        zone = dict(FULL_ZONE)
        zone["schedule"] = {"enabled": True, "days": [0], "start": "03:00", "end": "03:01"}

        with patch("feature_logic.loitering.time.time", return_value=1000.0):
            self._process([_box()], [79], zones=[zone])

        with patch("feature_logic.loitering.is_schedule_active", return_value=False):
            with patch("feature_logic.loitering.time.time", return_value=1065.0):
                dets = self._process([_box()], [79], zones=[zone])

        self.assertEqual(dets, [])

    def test_repeat_alert_respects_interval(self):
        """Second alert for same person must wait repeat_interval."""
        with patch("feature_logic.loitering.time.time", return_value=1000.0):
            self._process([_box()], [79])

        with patch("feature_logic.loitering.time.time", return_value=1061.0):
            dets1 = self._process([_box()], [79])
        self.assertEqual(len(dets1), 1)

        with patch("feature_logic.loitering.time.time", return_value=1100.0):
            dets2 = self._process([_box()], [79])
        self.assertEqual(dets2, [])

        with patch("feature_logic.loitering.time.time", return_value=1121.0):
            dets3 = self._process([_box()], [79])
        self.assertEqual(len(dets3), 1)

    def test_reentry_after_alert_does_not_inherit_dwell(self):
        """
        Real-world bug: loiterer (#1) triggers alert, leaves, a different person
        re-enters with the same track ID ~30s later — must NOT alert at the
        repeat interval with only ~30s of presence.
        """
        key = "cam_test::zone_test"
        pk = f"{key}::1"

        # Aditya loitered and was alerted at t=1061
        with patch("feature_logic.loitering.time.time", return_value=1000.0):
            self._process([_box()], [1])

        with patch("feature_logic.loitering.time.time", return_value=1061.0):
            dets1 = self._process([_box()], [1])
        self.assertEqual(len(dets1), 1)

        # Aditya left the zone; user re-enters with same track ID #1 later
        left_at = 1062.0
        _person_left_zone_at[pk] = left_at
        reentry_t = left_at + REENTRY_RESET_MIN_ABSENCE + 1.0
        with patch("feature_logic.loitering.time.time", return_value=reentry_t):
            dets_re = self._process([_box()], [1])
        self.assertEqual(dets_re, [])

        # 30s after user entered — must NOT fire repeat alert
        with patch("feature_logic.loitering.time.time", return_value=reentry_t + 30.0):
            dets2 = self._process([_box()], [1])
        self.assertEqual(dets2, [])

        # Fresh 60s dwell for the new entrant should alert at reentry + 60
        with patch("feature_logic.loitering.time.time", return_value=reentry_t + 61.0):
            dets3 = self._process([_box()], [1])
        self.assertEqual(len(dets3), 1)
        self.assertEqual(dets3[0]["dwell_seconds"], 61)

    def test_new_track_id_after_alerted_ghost_gets_fresh_timer(self):
        """New track ID must not inherit an alerted loiterer's dwell timer."""
        key = "cam_test::zone_test"
        ghost_pk = f"{key}::1"

        _person_entered[ghost_pk] = 900.0
        _person_last_seen[ghost_pk] = 950.0
        _person_last_alert[ghost_pk] = 961.0

        # New person #2 enters while ghost #1 is still grace-active
        t_now = 990.0
        with patch("feature_logic.loitering.time.time", return_value=t_now):
            dets = self._process([_box(cx=400)], [2])

        self.assertEqual(dets, [])
        pk2 = f"{key}::2"
        self.assertAlmostEqual(_person_entered[pk2], t_now, places=3)

        # 60s later #2 should alert on their own timer, not ghost's
        with patch("feature_logic.loitering.time.time", return_value=t_now + 61.0):
            dets2 = self._process([_box(cx=400)], [2])
        self.assertEqual(len(dets2), 1)
        self.assertEqual(dets2[0]["loitering_ids"], [2])
        self.assertEqual(dets2[0]["dwell_seconds"], 61)

    def test_two_people_both_tracked_and_alert(self):
        """Two people standing in zone must both appear in count and loitering_ids."""
        box_a = _box(cx=200, cy=300)
        box_b = _box(cx=440, cy=300)

        with patch("feature_logic.loitering.time.time", return_value=1000.0):
            self._process([box_a, box_b], [10, 11])

        with patch("feature_logic.loitering.time.time", return_value=1061.0):
            dets = self._process([box_a, box_b], [10, 11])

        self.assertEqual(len(dets), 1)
        det = dets[0]
        self.assertEqual(det["count"], 2)
        self.assertEqual(set(det["all_ids_in_zone"]), {10, 11})
        self.assertEqual(set(det["loitering_ids"]), {10, 11})

    def test_three_repeat_alerts_over_three_minutes(self):
        """Standing 3 min with 60s timer must fire alerts at ~60s, ~120s, ~180s."""
        with patch("feature_logic.loitering.time.time", return_value=1000.0):
            self._process([_box()], [79])

        alert_times = [1061.0, 1121.0, 1181.0]
        for t in alert_times:
            with patch("feature_logic.loitering.time.time", return_value=t):
                dets = self._process([_box()], [79])
            self.assertEqual(len(dets), 1, f"Expected alert at t={t}")
            self.assertIn(79, dets[0]["loitering_ids"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
