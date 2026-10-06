"""HES Trade Agent - POST-QUALITY-BASELINE signal gate v2.

This module replaces the old additive confirmation-count idea.
Correlated indicators are not independent votes; missing critical evidence is
NO_TRADE; and the signal requires separate context, structure, location,
trigger, confirmation and risk evidence.
"""
from dataclasses import dataclass
from enum import Enum


class QualityDecision(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class QualitySignalInput:
    data_valid: bool
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
    min_rr: float = 3.0


@dataclass(frozen=True)
class QualitySignalResult:
    decision: QualityDecision
    reasons: tuple[str, ...]


class PostQualityBaselineV2:
    """Strict gate-based signal generator.

    Unlike the legacy 3-of-N score, this does not allow several correlated
    indicators to manufacture a signal.
    """

    def evaluate(self, data: QualitySignalInput) -> QualitySignalResult:
        reasons: list[str] = []

        if not data.data_valid:
            return QualitySignalResult(QualityDecision.NO_TRADE, ("data_quality",))

        if data.direction not in ("long", "short"):
            return QualitySignalResult(QualityDecision.NO_TRADE, ("direction_missing",))

        direction = data.direction

        def require(condition: bool | None, reason: str) -> None:
            if condition is not True:
                reasons.append(reason)

        if data.htf_trend != direction:
            reasons.append("htf_trend_mismatch")
        require(data.htf_alignment, "htf_alignment_missing")

        if data.structure_bias != direction:
            reasons.append("structure_bias_mismatch")
        require(data.structure_break_confirmed, "structure_break_missing")

        require(data.location_valid, "location_invalid")
        require(data.liquidity_event_confirmed, "liquidity_confirmation_missing")

        require(data.entry_trigger_confirmed, "entry_trigger_missing")
        require(data.displacement_confirmed, "displacement_missing")

        if data.momentum_confirmed is not True and data.participation_confirmed is not True:
            reasons.append("independent_confirmation_missing")

        if data.contradiction is not False:
            reasons.append("contradiction_or_unknown")

        require(data.stop_valid, "invalid_stop")
        if data.rr is None or data.rr < data.min_rr:
            reasons.append("rr_below_minimum")

        if reasons:
            return QualitySignalResult(QualityDecision.NO_TRADE, tuple(reasons))

        return QualitySignalResult(
            QualityDecision.LONG if direction == "long" else QualityDecision.SHORT,
            (),
        )
