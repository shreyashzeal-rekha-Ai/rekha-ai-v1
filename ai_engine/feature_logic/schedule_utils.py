"""
feature_logic/schedule_utils.py
---------------------------------
Schedule enforcement utility for all AI features.

Schedule format (stored in cameras.json):
  {
    "enabled": true,
    "days":    [0, 1, 2, 3, 4],   # 0=Mon, 1=Tue, ... 6=Sun  (Python weekday())
    "start":   "09:00",
    "end":     "18:30"
  }

Usage:
  from feature_logic.schedule_utils import is_schedule_active

  if not is_schedule_active(cam_config.get("loitering_schedule")):
      return   # outside scheduled window → skip this feature
"""

import logging
from datetime import datetime, time as dtime, timezone, timedelta

# ── Strictly enforce Kolkata / IST timezone (UTC +05:30) ──────────────────────
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

logger = logging.getLogger("feature_logic.schedule_utils")


def _parse_hhmm(s: str) -> dtime:
    """Parse 'HH:MM' string into a datetime.time object."""
    try:
        h, m = s.split(":")
        return dtime(int(h), int(m))
    except Exception:
        return dtime(0, 0)


def is_schedule_active(schedule: dict | None) -> bool:
    """
    Returns True if the feature should be running right now.

    Rules:
      • If schedule is None or missing  → always active (no restriction)
      • If schedule["enabled"] == False → always active (user hasn't turned it on)
      • Otherwise check day-of-week and time window.

    Midnight-crossing windows (e.g. 22:00 → 06:00) are handled correctly.
    """
    if not schedule or not schedule.get("enabled", False):
        return True   # no schedule configured → run always

    now       = datetime.now(IST)
    today_dow = now.weekday()   # 0=Mon … 6=Sun

    allowed_days = schedule.get("days", list(range(7)))
    if today_dow not in allowed_days:
        logger.debug(f"[schedule] Skipping — today ({today_dow}) not in allowed days {allowed_days}")
        return False

    start_str = schedule.get("start", "00:00")
    end_str   = schedule.get("end",   "23:59")
    start     = _parse_hhmm(start_str)
    end       = _parse_hhmm(end_str)
    now_t     = now.time().replace(second=0, microsecond=0)

    if start <= end:
        # Normal window: e.g. 09:00 → 18:00
        active = start <= now_t <= end
    else:
        # Midnight-crossing window: e.g. 22:00 → 06:00
        active = now_t >= start or now_t <= end

    if not active:
        logger.debug(f"[schedule] Skipping — current time {now_t} outside {start_str}–{end_str}")

    return active
