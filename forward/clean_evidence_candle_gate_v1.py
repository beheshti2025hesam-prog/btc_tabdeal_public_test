"""Fail-closed candle boundary for clean forward evidence."""
from __future__ import annotations

from dataclasses import dataclass
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
    def __init__(
        self,
        *,
        source_completeness_verified: bool = False,
        source_completeness_evidence_ref: str | None = None,
        source_ordering_verified: bool = False,
        source_ordering_evidence_ref: str | None = None,
    ) -> None:
        self.source_completeness_verified = bool(
            source_completeness_verified
            and isinstance(source_completeness_evidence_ref, str)
            and source_completeness_evidence_ref.strip()
        )
        self.source_completeness_evidence_ref = source_completeness_evidence_ref
        self.source_ordering_verified = bool(
            source_ordering_verified
            and isinstance(source_ordering_evidence_ref, str)
            and source_ordering_evidence_ref.strip()
        )
        self.source_ordering_evidence_ref = source_ordering_evidence_ref

    def evaluate(self, records: list[dict[str, Any]], *, as_of) -> CleanEvidenceCandleResult:
        if not records:
            return CleanEvidenceCandleResult(False, (), (), "NO_FORWARD_RECORDS")

        sequence_result = CleanEvidenceSequenceGateV1(
            source_completeness_verified=self.source_completeness_verified,
            source_completeness_evidence_ref=self.source_completeness_evidence_ref,
            source_ordering_verified=self.source_ordering_verified,
            source_ordering_evidence_ref=self.source_ordering_evidence_ref,
        ).evaluate(records)
        if not sequence_result.safe:
            return CleanEvidenceCandleResult(False, (), (), sequence_result.reason or "SEQUENCE_UNSAFE")

        integration = SequenceAwareCandleIngestionV1(
            source_completeness_verified=self.source_completeness_verified,
            source_completeness_evidence_ref=self.source_completeness_evidence_ref,
            source_ordering_verified=self.source_ordering_verified,
            source_ordering_evidence_ref=self.source_ordering_evidence_ref,
        )
        try:
            result = integration.ingest(records, as_of=as_of)
        except (TypeError, ValueError):
            return CleanEvidenceCandleResult(False, (), (), "INVALID_FORWARD_INPUT")

        if not result.safe_for_decision:
            reason = next((event.reason for event in result.events if event.reason), None)
            return CleanEvidenceCandleResult(False, (), (), reason or "SEQUENCE_UNSAFE")
        return CleanEvidenceCandleResult(True, tuple(result.candles), tuple(result.gaps), "CANDLE_SAFE")
