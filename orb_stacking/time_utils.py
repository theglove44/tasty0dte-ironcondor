"""Timezone helpers for ORB Stacking.

All datetimes in the engine are UTC-aware. This module provides idempotent
conversions to/from ET and UK timezones for ORB lock-time comparisons and
human-readable logging.

Naive datetimes passed to these functions are assumed to be UTC.

Key concept: ORB lock bars
  - ORB lock events happen at fixed ET wall-clock times: 09:50, 10:00, 10:30 ET.
  - A 5-minute bar CLOSES at those times; its START is 5 minutes earlier.
  - ORB20 lock bar: START = 09:45 ET (closes at 09:50 ET)
  - ORB30 lock bar: START = 09:55 ET (closes at 10:00 ET)
  - ORB60 lock bar: START = 10:25 ET (closes at 10:30 ET)

  The is_lock_bar() function checks if a bar's start time matches these moments.
"""
from datetime import datetime, time
from typing import Dict
import pytz

UK_TZ = pytz.timezone('Europe/London')
ET_TZ = pytz.timezone('America/New_York')
UTC_TZ = pytz.UTC


def to_et(dt: datetime) -> datetime:
    """Convert datetime to ET. Idempotent.

    If dt is naive, treat it as UTC first.
    If dt is already ET-aware, return it unchanged.
    """
    if dt.tzinfo is None:
        dt = UTC_TZ.localize(dt)
    elif dt.tzinfo == ET_TZ:
        return dt

    return dt.astimezone(ET_TZ)


def to_uk(dt: datetime) -> datetime:
    """Convert datetime to UK timezone. Idempotent.

    If dt is naive, treat it as UTC first.
    If dt is already UK-aware, return it unchanged.
    """
    if dt.tzinfo is None:
        dt = UTC_TZ.localize(dt)
    elif dt.tzinfo == UK_TZ:
        return dt

    return dt.astimezone(UK_TZ)


def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC. Idempotent.

    If dt is naive, treat it as UTC first.
    If dt is already UTC-aware, return it unchanged.
    """
    if dt.tzinfo is None:
        return UTC_TZ.localize(dt)
    elif dt.tzinfo == UTC_TZ:
        return dt

    return dt.astimezone(UTC_TZ)


def lock_times_et() -> Dict[str, time]:
    """Return the ET wall-clock times when each ORB locks.

    Returns:
        dict mapping "ORB20" -> 09:50 ET, "ORB30" -> 10:00 ET, "ORB60" -> 10:30 ET.
    """
    return {
        "ORB20": time(9, 50),
        "ORB30": time(10, 0),
        "ORB60": time(10, 30),
    }


def is_lock_bar(bar_start: datetime, orb_name: str) -> bool:
    """Check if a bar whose START time is bar_start closes at the given ORB lock.

    The bar that CLOSES at a lock moment has a start 5 minutes earlier:
      - ORB20 lock bar: start = 09:45 ET
      - ORB30 lock bar: start = 09:55 ET
      - ORB60 lock bar: start = 10:25 ET

    Args:
        bar_start: the bar's start time (timezone-aware or naive UTC)
        orb_name: "ORB20", "ORB30", or "ORB60"

    Returns:
        True if bar_start (in ET) matches the expected lock-bar start moment.
    """
    lock_bar_starts = {
        "ORB20": time(9, 45),
        "ORB30": time(9, 55),
        "ORB60": time(10, 25),
    }

    if orb_name not in lock_bar_starts:
        return False

    bar_start_et = to_et(bar_start)
    target_start_time = lock_bar_starts[orb_name]

    # Compare hour and minute only (ignore seconds/microseconds)
    return (bar_start_et.hour == target_start_time.hour and
            bar_start_et.minute == target_start_time.minute)


def entry_window_closed(dt: datetime) -> bool:
    """Check if dt is at or after 12:00 ET (late-session entry dead zone).

    Per Doc1 §9, late-session breakouts after noon ET are effectively dead
    (26 in 21 years). Entry window closes at exactly 12:00 ET (midnight).

    Args:
        dt: the datetime to check (timezone-aware or naive UTC)

    Returns:
        True if dt >= 12:00 ET on the same trading day.
    """
    dt_et = to_et(dt)
    cutoff = time(12, 0)

    # Compare hour/minute (ignore seconds)
    current_time = time(dt_et.hour, dt_et.minute)
    return current_time >= cutoff
