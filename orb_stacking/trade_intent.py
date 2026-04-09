"""
Slice 8 — Trade intent dataclasses and skip event schema (SoT output contracts).

No runtime logic. Pure data containers consumed by Slices 9, 10, 12, 14.

Key design note: OrbSkipEvent.reason must hold the bare skip token (one of
SKIP_REASONS), not the full OrbBuilder gap message. When emitting a
bar_gap_during_lock skip, normalize OrbBuilder.gap_reason() output to the
bare "bar_gap_during_lock" token before constructing OrbSkipEvent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from orb_stacking.orb_levels import OrbLevels


SKIP_REASONS: frozenset[str] = frozenset({
    "no_breakout_before_noon",
    "orb20_close_middle_bear",
    "orb30_opposes_warning",
    "orb60_opposes_hard_exit",
    "base_tier_skip",
    "credit_too_low",
    "credit_too_high_flagged",
    "api_error",
    "calendar_blocked",
    "daily_cap",
    "bar_gap_during_lock",
})


@dataclass
class OrbTradeIntent:
    timestamp: datetime
    direction: str
    spread_side: str
    short_strike: float
    long_strike: float
    expected_credit: Optional[float]
    stack_tier: str
    base_tier: str
    contracts: int
    stack_score: int
    base_score: int
    calendar_score: int
    calendar_labels: list[str]
    closes_aligned_count: int
    range_expansion_ratio: float
    is_a_plus_buffer: bool
    is_immediate: bool
    orb20: OrbLevels
    orb30: Optional[OrbLevels] = None
    orb60: Optional[OrbLevels] = None
    notes: str = ""


@dataclass
class OrbSkipEvent:
    timestamp: datetime
    reason: str
    direction: Optional[str] = None
    orb20: Optional[OrbLevels] = None
    orb30: Optional[OrbLevels] = None
    orb60: Optional[OrbLevels] = None
    stack_tier: str = "FLAT"
    base_tier: Optional[str] = None
    notes: str = ""
