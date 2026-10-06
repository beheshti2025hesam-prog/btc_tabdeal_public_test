"""POST-QUALITY-BASELINE historical adapter.

This is intentionally conservative. The existing real-data backtest only
provides EMA/VWAP/pressure. It does NOT yet provide trustworthy HTF structure,
liquidity, displacement and entry-trigger features. Therefore this adapter
will emit NO_TRADE until those evidence families are explicitly available.

That is preferable to silently reusing the legacy baseline and manufacturing
signals from incomplete evidence.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from core.strategy.quality_signal import (
    PostQualityBaselineV2,
    QualityDecision,
    QualitySignalInput,
)


@dataclass(frozen=True)
class PostQualityObservation:
    timestamp: datetime
    direction: str | None
    htf_trend: str | None
    htf_alignment: bool | None
    structure_bias: str | None
    structure_break_confirmed: bool | None
    location_valid: bool | None
    liquidity_event_confirmed: bool | None
    entry_trigger_confirmed: bool | None
    displacement_confirmed: bool | None
    momentum_confirmed: bool | None
    participation_confirmed: bool | None
    contradiction: bool | None
    stop_valid: bool | None
    rr: float | None


@dataclass(frozen=True)
class PostQualityObservationResult:
    timestamp: datetime
    decision: QualityDecision
    reasons: tuple[str, ...]


class PostQualityHistoricalAdapter:
    """Evaluate complete evidence snapshots with hard NO_TRADE defaults."""

    def __init__(self) -> None:
        self.strategy = PostQualityBaselineV2()

    def evaluate(self, observation: PostQualityObservation) -> PostQualityObservationResult:
        result = self.strategy.evaluate(
            QualitySignalInput(
                data_valid=True,
                direction=observation.direction,
                htf_trend=observation.htf_trend,
                htf_alignment=observation.htf_alignment,
                structure_bias=observation.structure_bias,
                structure_break_confirmed=observation.structure_break_confirmed,
                location_valid=observation.location_valid,
                liquidity_event_confirmed=observation.liquidity_event_confirmed,
                entry_trigger_confirmed=observation.entry_trigger_confirmed,
                displacement_confirmed=observation.displacement_confirmed,
                momentum_confirmed=observation.momentum_confirmed,
                participation_confirmed=observation.participation_confirmed,
                contradiction=observation.contradiction,
                stop_valid=observation.stop_valid,
                rr=observation.rr,
            )
        )
        return PostQualityObservationResult(
            timestamp=observation.timestamp,
            decision=result.decision,
            reasons=result.reasons,
        )

    def evaluate_many(
        self, observations: Iterable[PostQualityObservation]
    ) -> list[PostQualityObservationResult]:
        return [self.evaluate(item) for item in observations]
