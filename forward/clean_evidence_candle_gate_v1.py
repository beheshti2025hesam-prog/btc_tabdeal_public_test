"""Fail-closed candle boundary for clean forward evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .sequence_candle_integration_v1 import SequenceCandleIntegrationV1


@dataclass(frozen=True)
class CleanEvidenceCandleResult:
    safe: bool
    candles: tuple[Any, ...]
    gaps: tuple[Any, ...]
    reason: str


class CleanEvidenceCandleGateV1:
    def evaluate(self, records: list[dict[str, Any]], *, as_of) -> CleanEvidenceCandleResult:
        if not records:
            return CleanEvidenceCandleResult(False, (), (), "NO_FORWARD_RECORDS")
        integration = SequenceCandleIntegrationV1()
        try:
            result = integration.process(records, as_of=as_of)
        except (TypeError, ValueError):
            return CleanEvidenceCandleResult(False, (), (), "INVALID_FORWARD_INPUT")
        if not result.safe_for_decision:
            return CleanEvidenceCandleResult(False, tuple(result.candles), tuple(result.gaps), result.reason or "SEQUENCE_UNSAFE")
        return CleanEvidenceCandleResult(True, tuple(result.candles), tuple(result.gaps), "CANDLE_SAFE")
