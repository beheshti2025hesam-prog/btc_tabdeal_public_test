"""Fail-closed candle boundary for clean forward evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .clean_evidence_sequence_gate_v1 import CleanEvidenceSequenceGateV1
from .sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1


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

        # Reject malformed, timezone-naive, or future timestamps before
        # sequence validation so diagnostics reflect the primary input defect.
        try:
            if as_of.tzinfo is None or as_of.utcoffset() is None:
                raise ValueError("as_of must be timezone-aware")
            for record in records:
                raw_timestamp = record.get("source_updated")
                if not isinstance(raw_timestamp, str):
                    raise ValueError("source_updated must be an ISO timestamp")
                observed_at = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
                if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                    raise ValueError("source_updated must be timezone-aware")
                if observed_at > as_of:
                    raise ValueError("future source observation")
        except (TypeError, ValueError, OverflowError, AttributeError):
            return CleanEvidenceCandleResult(False, (), (), "INVALID_FORWARD_INPUT")

        sequence_result = CleanEvidenceSequenceGateV1().evaluate(records)
        if not sequence_result.safe:
            return CleanEvidenceCandleResult(
                False, (), (), sequence_result.reason or "SEQUENCE_UNSAFE"
            )

        integration = SequenceAwareCandleIngestionV1()
        try:
            result = integration.ingest(records, as_of=as_of)
        except (TypeError, ValueError):
            return CleanEvidenceCandleResult(False, (), (), "INVALID_FORWARD_INPUT")

        if not result.safe_for_decision:
            return CleanEvidenceCandleResult(
                False, tuple(result.candles), tuple(result.gaps), "SEQUENCE_UNSAFE"
            )
        return CleanEvidenceCandleResult(
            True, tuple(result.candles), tuple(result.gaps), "CANDLE_SAFE"
        )
