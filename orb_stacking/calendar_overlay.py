"""Slice 6 — Calendar overlay scoring (SoT §2.8).

Hardcoded FOMC / triple-witching / OpEx date sets for 2025-2026 (2027 witching/opex
included), plus computed last-Friday-of-month and last-trading-day-of-quarter rules.

Pure functions. stdlib only (datetime, calendar). No I/O, no SDK, no async.
"""
from __future__ import annotations

import calendar
from datetime import date


# FOMC decision Wednesdays (tentative schedules published by the Fed Board).
# TODO: verify 2027 dates and populate 2028 before Dec 2027
_FOMC_WEDNESDAYS: frozenset[date] = frozenset({
    # 2025 (8 scheduled)
    date(2025, 1, 29),
    date(2025, 3, 19),
    date(2025, 5, 7),
    date(2025, 6, 18),
    date(2025, 7, 30),
    date(2025, 9, 17),
    date(2025, 10, 29),
    date(2025, 12, 10),
    # 2026 (8 scheduled)
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
    # 2027 (8 tentative)
    date(2027, 1, 27),
    date(2027, 3, 17),
    date(2027, 4, 28),
    date(2027, 6, 9),
    date(2027, 7, 28),
    date(2027, 9, 15),
    date(2027, 10, 27),
    date(2027, 12, 8),
})

# 3rd Friday of Mar/Jun/Sep/Dec each year
_TRIPLE_WITCHING_FRIDAYS: frozenset[date] = frozenset({
    date(2025, 3, 21), date(2025, 6, 20), date(2025, 9, 19), date(2025, 12, 19),
    date(2026, 3, 20), date(2026, 6, 19), date(2026, 9, 18), date(2026, 12, 18),
    date(2027, 3, 19), date(2027, 6, 18), date(2027, 9, 17), date(2027, 12, 17),
})

# 3rd Friday of every month
_OPEX_FRIDAYS: frozenset[date] = frozenset({
    # 2025
    date(2025, 1, 17), date(2025, 2, 21), date(2025, 3, 21), date(2025, 4, 18),
    date(2025, 5, 16), date(2025, 6, 20), date(2025, 7, 18), date(2025, 8, 15),
    date(2025, 9, 19), date(2025, 10, 17), date(2025, 11, 21), date(2025, 12, 19),
    # 2026
    date(2026, 1, 16), date(2026, 2, 20), date(2026, 3, 20), date(2026, 4, 17),
    date(2026, 5, 15), date(2026, 6, 19), date(2026, 7, 17), date(2026, 8, 21),
    date(2026, 9, 18), date(2026, 10, 16), date(2026, 11, 20), date(2026, 12, 18),
    # 2027
    date(2027, 1, 15), date(2027, 2, 19), date(2027, 3, 19), date(2027, 4, 16),
    date(2027, 5, 21), date(2027, 6, 18), date(2027, 7, 16), date(2027, 8, 20),
    date(2027, 9, 17), date(2027, 10, 15), date(2027, 11, 19), date(2027, 12, 17),
})

SCORE_CLAMP_MIN: int = -2
SCORE_CLAMP_MAX: int = 2


def _is_last_trading_day_of_quarter(d: date) -> bool:
    """True iff d is the last weekday (Mon-Fri) of Mar/Jun/Sep/Dec.

    Does not account for NYSE holidays (out of scope).

    Args:
        d: The date to test.

    Returns:
        True if d is the last Mon-Fri of a quarter-end month.
    """
    if d.month not in (3, 6, 9, 12):
        return False
    if d.weekday() >= 5:  # Sat/Sun cannot be last trading day
        return False
    last_day_num = calendar.monthrange(d.year, d.month)[1]
    day = last_day_num
    while True:
        candidate = date(d.year, d.month, day)
        if candidate.weekday() < 5:
            return candidate == d
        day -= 1


def _is_last_friday_of_month(d: date) -> bool:
    """True iff d is the last Friday of its month.

    Args:
        d: The date to test.

    Returns:
        True if d is a Friday and no later Friday exists in the same month.
    """
    if d.weekday() != 4:  # 4 = Friday
        return False
    last_day_num = calendar.monthrange(d.year, d.month)[1]
    return d.day + 7 > last_day_num


def calendar_score(d: date) -> tuple[int, list[str]]:
    """Score a trading day per SoT §2.8 calendar overlay.

    Rules (sum then clamp to [-2, +2]):
      +1  FOMC decision Wednesday
      +1  last trading day of quarter (Mar/Jun/Sep/Dec)
      +1  last Friday of month
      -2  triple-witching Friday (3rd Fri of Mar/Jun/Sep/Dec)
      -1  OpEx Friday (3rd Fri of any month) — NOT applied on triple-witching
          days to avoid double-counting the expiry penalty.

    Args:
        d: The trading date to score.

    Returns:
        (clamped_score, labels) where labels are appended in rule order:
        FOMC → quarter_end → last_friday → triple_witching/opex.
        Empty labels list iff no rules fire.
    """
    score = 0
    labels: list[str] = []

    if d in _FOMC_WEDNESDAYS:
        score += 1
        labels.append("FOMC")

    if _is_last_trading_day_of_quarter(d):
        score += 1
        labels.append("quarter_end")

    if _is_last_friday_of_month(d):
        score += 1
        labels.append("last_friday")

    is_triple = d in _TRIPLE_WITCHING_FRIDAYS
    if is_triple:
        score -= 2
        labels.append("triple_witching")
    elif d in _OPEX_FRIDAYS:
        score -= 1
        labels.append("opex")

    clamped = max(SCORE_CLAMP_MIN, min(SCORE_CLAMP_MAX, score))
    return clamped, labels
