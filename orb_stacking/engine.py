"""Slice 11 — OrbStackingEngine: full engine assembly.

Wires ATR(14), StackingEngine (Slices 2–4), strike selector (Slice 5),
range expansion + calendar (Slice 6), grader (Slice 7), trade intent
(Slice 8), sizing (Slice 9) into one stateful engine.

Public interface:
    engine = OrbStackingEngine()
    events = engine.on_closed_bar(bar)  # list of OrbTradeIntent | OrbSkipEvent
    engine.reset_for_new_session()

Caller responsibilities:
  - Call `reset_for_new_session()` FIRST (it wipes `_atr`), THEN feed exactly
    14 prior DAILY bars to `_atr.update`, THEN call `on_closed_bar`. ATR(14)
    per Doc1 §7 is a DAILY-range indicator, not a 5m-range indicator.
  - 5m bars must have keys: "start" (datetime UTC), "open", "high", "low", "close", "volume"
  - Pass bars in chronological order.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Optional, Union

from orb_stacking.breakout import immediate_breakout
from orb_stacking.calendar_overlay import calendar_score as _calendar_score
from orb_stacking.grader import GraderInputs, grade_base_setup
from orb_stacking.indicators import ATR
from orb_stacking.orb_levels import GAP_REASON, ORB_NAMES, OrbLevels
from orb_stacking.range_expansion import range_expansion_ratio
from orb_stacking.sizing import compute_contracts
from orb_stacking.stacking import StackingEngine, StackingEvent
from orb_stacking.strike_selector import select_spread
from orb_stacking.time_utils import to_et
from orb_stacking.trade_intent import OrbSkipEvent, OrbTradeIntent


_STACK_SCORE: dict[str, int] = {
    "FLAT": 0, "HALF": 1, "NORMAL": 2, "PLUS": 3, "DOUBLE": 4, "EXITED": 0,
}


class OrbStackingEngine:
    """Full ORB stacking engine. Stateful; call reset_for_new_session() each morning."""

    def __init__(self) -> None:
        self._atr = ATR(14)
        self._stacking = StackingEngine()
        self._session_date: Optional[date] = None
        self._cal_score: int = 0
        self._cal_labels: list[str] = []
        self._base_grade: Optional[dict] = None
        self._direction: Optional[str] = None
        self._spread = None
        self._current_intent: Optional[OrbTradeIntent] = None
        self._aborted: bool = False
        self._gap_emitted: set[str] = set()
        self._timeout_noon_emitted: bool = False

    def reset_for_new_session(self) -> None:
        """Reset all per-session state. Call once before feeding a new day's bars."""
        self._stacking.reset_for_new_session()
        self._atr.reset()
        self._session_date = None
        self._cal_score = 0
        self._cal_labels = []
        self._base_grade = None
        self._direction = None
        self._spread = None
        self._current_intent = None
        self._aborted = False
        self._gap_emitted = set()
        self._timeout_noon_emitted = False

    def on_closed_bar(self, bar: dict) -> list[Union[OrbTradeIntent, OrbSkipEvent]]:
        """Process one closed 5-minute bar.

        Returns a (possibly empty) list of OrbTradeIntent or OrbSkipEvent objects
        emitted in response to this bar.
        """
        if self._aborted:
            return []

        results: list[Union[OrbTradeIntent, OrbSkipEvent]] = []

        if self._session_date is None:
            self._session_date = to_et(bar["start"]).date()
            self._cal_score, self._cal_labels = _calendar_score(self._session_date)

        # Gap-before-stack ordering contract
        # ─────────────────────────────────
        # `_stacking.on_closed_bar` is called first because gap_reason() is
        # populated *inside* that call (OrbBuilder sets it when a bar arrives
        # at or after the lock-boundary time, whether that is the boundary bar
        # itself or a later bar that first crosses it).
        # The gap-check loop below appends any OrbSkipEvent(reason=GAP_REASON)
        # to `results` before the stack-event dispatch loop appends its events,
        # so the output contract — gap skips precede stack-derived events — holds.
        #
        # Mutual-exclusivity note: a gapped ORB is marked SKIPPED (not LOCKED),
        # so StackingEngine will never emit ORB20_BREAK / ORB30_CONFIRM /
        # ORB60_CONFIRM for an ORB that has a gap. On any bar where gaps and stack
        # events coexist (e.g. ORB20/30/60 all gapped + TIMEOUT_NOON fires), the
        # gap skips always land in `results` before the timeout skip.

        stack_events = self._stacking.on_closed_bar(bar)

        orb_builder = self._stacking.orb_builder
        bar_ts = bar["start"]
        for name in ORB_NAMES:
            if name in self._gap_emitted:
                continue
            if orb_builder.gap_reason(name) is not None:
                self._gap_emitted.add(name)
                results.append(OrbSkipEvent(
                    timestamp=bar_ts,
                    reason=GAP_REASON,
                    direction=self._direction,
                    orb20=orb_builder.locked("ORB20"),
                    orb30=orb_builder.locked("ORB30"),
                    orb60=orb_builder.locked("ORB60"),
                    stack_tier=self._stacking.current_tier,
                    base_tier=self._base_grade["tier"] if self._base_grade else None,
                    notes=f"{name} gap",
                ))

        _handlers = {
            "ORB20_BREAK": self._on_orb20_break,
            "ORB30_CONFIRM": self._on_orb30_confirm,
            "ORB30_OPPOSE": self._on_orb30_oppose,
            "ORB60_CONFIRM": self._on_orb60_confirm,
            "ORB60_OPPOSE": self._on_orb60_oppose,
            "TIMEOUT_NOON": self._on_timeout_noon,
            "ORB60_NO_BREAKOUT": None,
        }
        for ev in stack_events:
            if self._aborted:
                break
            handler = _handlers.get(ev.kind)
            if handler is None:
                continue
            out = handler(ev)
            if out is not None:
                if isinstance(out, list):
                    results.extend(out)
                else:
                    results.append(out)

        return results

    def _on_orb20_break(self, ev: StackingEvent) -> Optional[Union[OrbTradeIntent, OrbSkipEvent]]:
        if self._atr.value is None:
            self._aborted = True
            return OrbSkipEvent(
                timestamp=ev.timestamp,
                reason="atr_not_ready",
                direction=ev.direction,
                stack_tier=ev.state_snapshot.get("stack_tier", "FLAT"),
                notes="atr_not_ready",
            )

        self._direction = ev.direction

        try:
            sel = select_spread(ev.orb, self._direction)
        except ValueError as exc:
            self._aborted = True
            return OrbSkipEvent(
                timestamp=ev.timestamp,
                reason="api_error",
                direction=self._direction,
                orb20=ev.orb,
                stack_tier=ev.state_snapshot.get("stack_tier", "FLAT"),
                notes=str(exc),
            )

        if sel.buffer < 0:
            self._aborted = True
            return OrbSkipEvent(
                timestamp=ev.timestamp,
                reason="credit_too_low",
                direction=self._direction,
                orb20=ev.orb,
                stack_tier=ev.state_snapshot.get("stack_tier", "FLAT"),
                notes=f"buffer={sel.buffer:.2f}",
            )

        self._spread = sel

        is_imm = immediate_breakout(self._stacking.orb20_breakout) if self._stacking.orb20_breakout else False
        grader_in = GraderInputs(
            orb20=ev.orb,
            direction=self._direction,
            breakout_timing_immediate=is_imm,
            atr14=self._atr.value,
            day_of_week=self._session_date.weekday(),
            buffer_dollars=sel.buffer,
        )
        self._base_grade = grade_base_setup(grader_in)

        sizing = compute_contracts("HALF", self._base_grade["tier"], self._cal_score)

        intent = OrbTradeIntent(
            timestamp=ev.timestamp,
            direction=self._direction,
            spread_side=sel.spread_type,
            short_strike=float(sel.short_strike),
            long_strike=float(sel.long_strike),
            expected_credit=None,
            stack_tier="HALF",
            base_tier=self._base_grade["tier"],
            contracts=sizing["contracts"],
            stack_score=_STACK_SCORE["HALF"],
            base_score=self._base_grade["score"],
            calendar_score=self._cal_score,
            calendar_labels=list(self._cal_labels),
            closes_aligned_count=ev.state_snapshot.get("closes_aligned", 0),
            range_expansion_ratio=1.0,
            is_a_plus_buffer=sel.is_a_plus,
            is_immediate=is_imm,
            orb20=ev.orb,
        )
        self._current_intent = intent
        return intent

    def _on_orb30_confirm(self, ev: StackingEvent) -> Optional[OrbTradeIntent]:
        if self._current_intent is None:
            return None
        stack_tier = "NORMAL"
        sizing = compute_contracts(stack_tier, self._base_grade["tier"], self._cal_score)
        intent = dataclasses.replace(
            self._current_intent,
            timestamp=ev.timestamp,
            stack_tier=stack_tier,
            stack_score=_STACK_SCORE[stack_tier],
            contracts=sizing["contracts"],
            closes_aligned_count=ev.state_snapshot.get("closes_aligned", 0),
            orb30=ev.orb,
        )
        self._current_intent = intent
        return intent

    def _on_orb30_oppose(self, ev: StackingEvent) -> OrbSkipEvent:
        orb_b = self._stacking.orb_builder
        return OrbSkipEvent(
            timestamp=ev.timestamp,
            reason="orb30_opposes_warning",
            direction=self._direction,
            orb20=orb_b.locked("ORB20"),
            orb30=ev.orb,
            stack_tier=ev.state_snapshot.get("stack_tier", "FLAT"),
            base_tier=self._base_grade["tier"] if self._base_grade else None,
        )

    def _on_orb60_confirm(self, ev: StackingEvent) -> Optional[OrbTradeIntent]:
        if self._current_intent is None:
            return None
        stack_tier = ev.state_snapshot.get("stack_tier", "PLUS")
        orb60 = ev.orb
        try:
            re_ratio = range_expansion_ratio(self._current_intent.orb20, orb60)
        except ValueError:
            re_ratio = 1.0
        sizing = compute_contracts(stack_tier, self._base_grade["tier"], self._cal_score)
        intent = dataclasses.replace(
            self._current_intent,
            timestamp=ev.timestamp,
            stack_tier=stack_tier,
            stack_score=_STACK_SCORE.get(stack_tier, 0),
            contracts=sizing["contracts"],
            closes_aligned_count=ev.state_snapshot.get("closes_aligned", 0),
            range_expansion_ratio=re_ratio,
            orb60=orb60,
        )
        self._current_intent = intent
        return intent

    def _on_orb60_oppose(self, ev: StackingEvent) -> OrbSkipEvent:
        orb_b = self._stacking.orb_builder
        return OrbSkipEvent(
            timestamp=ev.timestamp,
            reason="orb60_opposes_hard_exit",
            direction=self._direction,
            orb20=orb_b.locked("ORB20"),
            orb30=orb_b.locked("ORB30"),
            orb60=ev.orb,
            stack_tier=ev.state_snapshot.get("stack_tier", "FLAT"),
            base_tier=self._base_grade["tier"] if self._base_grade else None,
        )

    def _on_timeout_noon(self, ev: StackingEvent) -> Optional[OrbSkipEvent]:
        if self._timeout_noon_emitted:
            return None
        self._timeout_noon_emitted = True
        return OrbSkipEvent(
            timestamp=ev.timestamp,
            reason="no_breakout_before_noon",
            direction=self._direction,
            stack_tier=self._stacking.current_tier,
        )
