"""Slice 10 — Hard-exit signal derivation and bracket level computation.

Pure functions. No I/O, no SDK, no async. Consumes StackingEvent
(Slice 4) and emits bracket levels or an optional HardExitSignal.

IMPORTANT — position_tier_before semantics:
  StackingEngine calls _set_tier() BEFORE building the state_snapshot.
  For ORB60_OPPOSE the snapshot already shows "EXITED"; for ORB30_OPPOSE
  the tier is unchanged (engine doesn't downgrade on oppose), so snapshot
  still holds the pre-oppose tier. position_tier_before is taken verbatim
  from event.state_snapshot["stack_tier"].
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from orb_stacking.stacking import StackingEvent


REASON_ORB60_OPPOSES = "orb60_opposes"
REASON_ORB30_OPPOSES_REDUCE = "orb30_opposes_reduce"


@dataclass
class HardExitSignal:
    """Signal emitted when a stacking event triggers a hard exit or reduce.

    Attributes:
        reason: "orb60_opposes" (full exit) or "orb30_opposes_reduce" (reduce to HALF).
        timestamp: UTC timestamp from the originating StackingEvent.
        position_tier_before: stack_tier as recorded in event.state_snapshot.
        position_tier_after: "EXITED" for ORB60_OPPOSE, "HALF" for ORB30_OPPOSE.
    """
    reason: str
    timestamp: datetime
    position_tier_before: str
    position_tier_after: str


def bracket_levels(
    entry_credit: float,
    target_pct: float = 0.50,
    stop_mult: float = 2.0,
) -> dict:
    """Compute bracket OCO target and stop debit levels.

    Args:
        entry_credit: The credit received when entering the spread (must be >= 0).
        target_pct: Fraction of credit to target as profit. Default 0.50 (50%).
        stop_mult: Multiplier on credit for the stop loss. Default 2.0 (200%).

    Returns:
        Dict with keys:
          target_debit (float): entry_credit * target_pct
          stop_debit   (float): entry_credit * stop_mult

    Raises:
        ValueError: If entry_credit < 0, target_pct < 0, or stop_mult < 0.
    """
    if entry_credit < 0:
        raise ValueError(f"entry_credit must be non-negative, got {entry_credit}")
    if target_pct < 0:
        raise ValueError(f"target_pct must be non-negative, got {target_pct}")
    if stop_mult < 0:
        raise ValueError(f"stop_mult must be non-negative, got {stop_mult}")
    return {
        "target_debit": entry_credit * target_pct,
        "stop_debit":   entry_credit * stop_mult,
    }


def evaluate_exit_signal(event: StackingEvent) -> Optional[HardExitSignal]:
    """Derive a hard-exit or reduce signal from a StackingEvent.

    Rules (SoT §2.4, §2.7):
      ORB60_OPPOSE → full exit (reason="orb60_opposes", tier_after="EXITED")
      ORB30_OPPOSE → reduce warning (reason="orb30_opposes_reduce", tier_after="HALF")
      All other kinds → None

    Note: position_tier_before is read from event.state_snapshot["stack_tier"].
    For ORB60_OPPOSE this will be "EXITED" because StackingEngine already
    applied _set_tier("EXITED") before snapshotting.

    Args:
        event: A StackingEvent from StackingEngine.on_closed_bar().

    Returns:
        HardExitSignal if the event triggers an exit/reduce, else None.
    """
    tier_before = event.state_snapshot.get("stack_tier", "FLAT")

    if event.kind == "ORB60_OPPOSE":
        return HardExitSignal(
            reason=REASON_ORB60_OPPOSES,
            timestamp=event.timestamp,
            position_tier_before=tier_before,
            position_tier_after="EXITED",
        )

    if event.kind == "ORB30_OPPOSE":
        return HardExitSignal(
            reason=REASON_ORB30_OPPOSES_REDUCE,
            timestamp=event.timestamp,
            position_tier_before=tier_before,
            position_tier_after="HALF",
        )

    return None
