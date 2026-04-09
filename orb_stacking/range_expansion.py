"""Slice 6 — Range expansion ratio and bonus (SoT §2.5).

Pure functions. Imports only orb_stacking.orb_levels.
No I/O, no SDK, no async.
"""
from __future__ import annotations

from orb_stacking.orb_levels import OrbLevels


EXPANSION_BONUS_THRESHOLD: float = 2.5


def range_expansion_ratio(orb20: OrbLevels, orb60: OrbLevels) -> float:
    """Ratio of ORB60 range to ORB20 range.

    Args:
        orb20: The ORB20 levels.
        orb60: The ORB60 levels.

    Returns:
        orb60.range / orb20.range.

    Raises:
        ValueError: If orb20.range == 0 (would otherwise produce inf).
    """
    if orb20.range == 0:
        raise ValueError("orb20.range is zero; expansion ratio undefined")
    return orb60.range / orb20.range


def expansion_bonus(ratio: float) -> int:
    """Score bonus for range expansion (SoT §2.5).

    Args:
        ratio: The expansion ratio (ORB60 range / ORB20 range).

    Returns:
        1 if ratio >= 2.5 (inclusive), else 0.
    """
    return 1 if ratio >= EXPANSION_BONUS_THRESHOLD else 0
