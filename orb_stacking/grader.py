"""Slice 7 — Base setup grading and tier assignment (SoT §2.9).

Pure functions with no I/O, no SDK, no async. Consumes an OrbLevels plus
context (direction, ATR, day of week, buffer) and returns a grade score,
tier label, and a per-factor breakdown.

Factor rules (SoT §2.9):
  1. ORB20 range / ATR14 ratio:
       < 0.20              -> +2
       0.20 <= r <= 0.30   -> +1   (both boundaries inclusive)
       0.30 <  r <= 0.40   ->  0
       > 0.40              -> -1
     atr14 == 0 raises ValueError.
  2. breakout_timing_immediate == True -> +1, else 0.
  3. ORB20 close aligned with direction:
       bull: close_pct >= 0.80 -> +1
       bear: close_pct <= 0.20 -> +1
       close_pct is None       -> 0 (no alignment bonus)
  4. Day of week:
       Thu (3) or Fri (4) -> +1
       Mon (0)            -> -1
       All other days     ->  0  (Tue killed by Doc4)
  5. Buffer dollars:
       >= 4.0           -> +1
       <  1.0           -> -1
       [1.0, 4.0)       ->  0

Tier mapping:
  score <= -1      -> "HALF"
  0 <= score <= 1  -> "NORMAL"
  2 <= score <= 3  -> "PLUS"
  score >= 4       -> "DOUBLE"

Imports: dataclasses, orb_stacking.orb_levels only.
"""
from __future__ import annotations

from dataclasses import dataclass

from orb_stacking.orb_levels import OrbLevels


# Factor thresholds
ATR_RATIO_BIN_VERY_LOW: float = 0.20   # ratio < this -> +2
ATR_RATIO_BIN_LOW: float = 0.30        # ratio <= this (and >= 0.20) -> +1
ATR_RATIO_BIN_MID: float = 0.40        # ratio <= this (and > 0.30) -> 0

CLOSE_PCT_BULL_THRESHOLD: float = 0.80
CLOSE_PCT_BEAR_THRESHOLD: float = 0.20

BUFFER_HIGH_THRESHOLD: float = 4.0
BUFFER_LOW_THRESHOLD: float = 1.0

# Day of week constants (Python datetime convention: Mon=0 .. Sun=6)
_MONDAY = 0
_THURSDAY = 3
_FRIDAY = 4

# Tier labels
TIER_HALF = "HALF"
TIER_NORMAL = "NORMAL"
TIER_PLUS = "PLUS"
TIER_DOUBLE = "DOUBLE"


@dataclass
class GraderInputs:
    """Inputs to the base setup grader.

    Attributes:
        orb20: The locked ORB20 levels.
        direction: "bull" or "bear".
        breakout_timing_immediate: True if breakout occurred on the lock bar.
        atr14: ATR(14) at lock time. Must be > 0.
        day_of_week: Python weekday (0=Mon .. 6=Sun).
        buffer_dollars: A+ buffer distance in dollars (may be negative).
    """
    orb20: OrbLevels
    direction: str
    breakout_timing_immediate: bool
    atr14: float
    day_of_week: int
    buffer_dollars: float


def _score_orb_atr_ratio(ratio: float) -> int:
    """Score the ORB20-range / ATR14 ratio per SoT §2.9.

    Boundaries:
      ratio < 0.20              -> +2
      0.20 <= ratio <= 0.30     -> +1   (both ends inclusive)
      0.30 <  ratio <= 0.40     ->  0
      ratio > 0.40              -> -1
    """
    if ratio < ATR_RATIO_BIN_VERY_LOW:
        return 2
    if ratio <= ATR_RATIO_BIN_LOW:
        return 1
    if ratio <= ATR_RATIO_BIN_MID:
        return 0
    return -1


def _score_close_alignment(close_pct: float | None, direction: str) -> int:
    """Score ORB20 close alignment with the trade direction.

    Args:
        close_pct: ORB20 close_pct (may be None if range == 0).
        direction: "bull" or "bear".

    Returns:
        +1 if aligned, 0 otherwise.

    Raises:
        ValueError: If direction is not "bull" or "bear".
    """
    if direction not in ("bull", "bear"):
        raise ValueError(f"direction must be 'bull' or 'bear', got {direction!r}")
    if close_pct is None:
        return 0
    if direction == "bull":
        return 1 if close_pct >= CLOSE_PCT_BULL_THRESHOLD else 0
    # bear
    return 1 if close_pct <= CLOSE_PCT_BEAR_THRESHOLD else 0


def _score_day_of_week(day_of_week: int) -> int:
    """Score the day-of-week factor.

    Thu/Fri -> +1, Mon -> -1, all others -> 0 (Doc4 killed Tuesday).
    """
    if day_of_week in (_THURSDAY, _FRIDAY):
        return 1
    if day_of_week == _MONDAY:
        return -1
    return 0


def _score_buffer(buffer_dollars: float) -> int:
    """Score the A+ buffer distance.

    >= 4.0 -> +1, < 1.0 -> -1, [1.0, 4.0) -> 0.
    """
    if buffer_dollars >= BUFFER_HIGH_THRESHOLD:
        return 1
    if buffer_dollars < BUFFER_LOW_THRESHOLD:
        return -1
    return 0


def _tier_for_score(score: int) -> str:
    """Map a raw score to a tier label per SoT §2.9."""
    if score <= -1:
        return TIER_HALF
    if score <= 1:
        return TIER_NORMAL
    if score <= 3:
        return TIER_PLUS
    return TIER_DOUBLE


def grade_base_setup(inputs: GraderInputs) -> dict:
    """Grade a base setup and assign a sizing tier.

    Args:
        inputs: The GraderInputs bundle.

    Returns:
        Dict with keys:
          - "score" (int): sum of all factor points.
          - "tier" (str): one of "HALF", "NORMAL", "PLUS", "DOUBLE".
          - "factors_breakdown" (dict): per-factor points plus the raw
            ORB/ATR ratio. Always contains all keys:
              "orb_atr_ratio", "orb_atr_points", "immediate_points",
              "close_aligned_points", "dow_points", "buffer_points".

    Raises:
        ValueError: If atr14 <= 0 or direction is invalid.
    """
    if inputs.atr14 <= 0:
        raise ValueError(f"atr14 must be positive, got {inputs.atr14}")

    ratio = inputs.orb20.range / inputs.atr14
    orb_atr_points = _score_orb_atr_ratio(ratio)
    immediate_points = 1 if inputs.breakout_timing_immediate else 0
    close_aligned_points = _score_close_alignment(
        inputs.orb20.close_pct, inputs.direction
    )
    dow_points = _score_day_of_week(inputs.day_of_week)
    buffer_points = _score_buffer(inputs.buffer_dollars)

    score = (
        orb_atr_points
        + immediate_points
        + close_aligned_points
        + dow_points
        + buffer_points
    )
    tier = _tier_for_score(score)

    return {
        "score": score,
        "tier": tier,
        "factors_breakdown": {
            "orb_atr_ratio": ratio,
            "orb_atr_points": orb_atr_points,
            "immediate_points": immediate_points,
            "close_aligned_points": close_aligned_points,
            "dow_points": dow_points,
            "buffer_points": buffer_points,
        },
    }
