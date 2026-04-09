"""Slice 5 — Strike selection and A+ buffer classification.

Pure functions with no I/O, no SDK, no async. Consumes OrbLevels and
direction strings; returns primitives and frozen dataclasses.

Imports: dataclasses, typing, orb_stacking.orb_levels only.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Literal

from orb_stacking.orb_levels import OrbLevels


# Constants
STRIKE_GRID: float = 5.0
SPREAD_WIDTH: int = 5
A_PLUS_BUFFER_THRESHOLD: float = 4.0
MIN_VALID_CREDIT: float = 0.80
CAUTION_CREDIT_THRESHOLD: float = 1.50

Direction = Literal["bull", "bear"]


@dataclass(frozen=True)
class SpreadSelection:
    """Result of selecting a credit spread around an ORB20 midpoint.

    direction: "bull" (put spread) or "bear" (call spread).
    short_strike: Nearest $5 strike to ORB20 midpoint.
    long_strike: Protective wing, $5 away on the spread's risk side
        (short - 5 for bull put, short + 5 for bear call).
    spread_type: "put" for bull, "call" for bear.
    buffer: Distance from ORB20 protective level (high for bull,
        low for bear) to the short strike. May be negative.
    is_a_plus: True iff buffer >= 4.0.
    """
    direction: Direction
    short_strike: int
    long_strike: int
    spread_type: Literal["put", "call"]
    buffer: float
    is_a_plus: bool


@dataclass(frozen=True)
class CreditValidation:
    """Result of validating a spread credit against SoT §2.6 bands.

    credit: The credit passed in, unchanged.
    is_valid: False iff credit < 0.80.
    reason: "skip: credit < 0.80" | "ok" | "caution: credit > 1.50".
    """
    credit: float
    is_valid: bool
    reason: str


def select_short_strike(midpoint: float, grid: float = STRIKE_GRID) -> int:
    """Round midpoint to nearest grid boundary.

    Args:
        midpoint: The price level to round.
        grid: The grid spacing (default 5.0). May be non-integer (e.g. 1.0 for
            XSP). Uses Python's banker's rounding at exact half-grid ties; for
            SPX (integer+fraction midpoints on a $5 grid), this is
            deterministic and ties are vanishingly rare in practice.

    Returns:
        Nearest grid boundary as int.

    Raises:
        ValueError: If grid <= 0.
    """
    if grid <= 0:
        raise ValueError(f"grid must be positive, got {grid}")
    return int(round(midpoint / grid) * grid)


def buffer_to_nearest_5(level: float) -> float:
    """Distance from a price level to the nearest $5 boundary.

    Always in [0.0, 2.5].

    Args:
        level: The price level.

    Returns:
        Minimum distance to a $5 boundary.
    """
    remainder = level % 5
    return min(remainder, 5 - remainder)


def compute_a_plus_buffer(orb20: OrbLevels, short_strike: int, direction: Direction) -> float:
    """Distance from ORB20 protective level to short strike.

    Bull: high - short_strike
    Bear: short_strike - low

    Args:
        orb20: The ORB20 levels.
        short_strike: The short strike price.
        direction: "bull" (put spread) or "bear" (call spread).

    Returns:
        Buffer distance, may be negative.

    Raises:
        ValueError: If direction is not "bull" or "bear".
    """
    if direction == "bull":
        return orb20.high - short_strike
    elif direction == "bear":
        return short_strike - orb20.low
    else:
        raise ValueError(f"direction must be 'bull' or 'bear', got {direction!r}")


def is_a_plus_setup(buffer: float) -> bool:
    """Check if buffer meets A+ threshold.

    Args:
        buffer: The buffer distance.

    Returns:
        True iff buffer >= 4.0.
    """
    return buffer >= A_PLUS_BUFFER_THRESHOLD


def select_spread(orb20: OrbLevels, direction: Direction) -> SpreadSelection:
    """Select a credit spread around ORB20 midpoint.

    Args:
        orb20: The ORB20 levels.
        direction: "bull" (put spread) or "bear" (call spread).

    Returns:
        SpreadSelection with strikes, spread type, buffer, and A+ flag.

    Raises:
        ValueError: If direction is invalid.
    """
    if direction not in ("bull", "bear"):
        raise ValueError(f"direction must be 'bull' or 'bear', got {direction!r}")

    short = select_short_strike(orb20.midpoint)

    if direction == "bull":
        long_strike = short - SPREAD_WIDTH
        spread_type = "put"
    else:  # bear
        long_strike = short + SPREAD_WIDTH
        spread_type = "call"

    buffer = compute_a_plus_buffer(orb20, short, direction)

    return SpreadSelection(
        direction=direction,
        short_strike=short,
        long_strike=long_strike,
        spread_type=spread_type,
        buffer=buffer,
        is_a_plus=is_a_plus_setup(buffer),
    )


def validate_credit(credit: float) -> CreditValidation:
    """Validate a spread credit against SoT §2.6 bands.

    Args:
        credit: The credit value.

    Returns:
        CreditValidation with validity flag and reason.

    Raises:
        ValueError: If credit is not a finite number (NaN or inf).
    """
    if not math.isfinite(credit):
        raise ValueError(f"credit must be a finite number, got {credit!r}")
    if credit < MIN_VALID_CREDIT:
        return CreditValidation(credit, False, "skip: credit < 0.80")
    elif credit > CAUTION_CREDIT_THRESHOLD:
        return CreditValidation(credit, True, "caution: credit > 1.50")
    else:
        return CreditValidation(credit, True, "ok")
