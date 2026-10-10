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
        sequence_contract_verified: bool = False,
        sequence_contract_evidence_ref: str | None = None,
    ) -> None:
        self.sequence_contract_verified = bool(
            sequence_contract_verified and sequence_contract_evidence_ref
        )
        self.sequence_contract_evidence_ref = sequence_contract_evidence_ref

    def evaluate(self, records: list[dict[str, Any]], *, as_of) -> CleanEvidenceCandleResult:
        if not records:
            return CleanEvidenceCandleResult(False, (), (), "NO_FORWARD_RECORDS")

        sequence_result = CleanEvidenceSequenceGateV1(
            sequence_contract_verified=self.sequence_contract_verified,
            sequence_contract_evidence_ref=self.sequence_contract_evidence_ref,
        ).evaluate(records)
        if not sequence_result.safe:
            return CleanEvidenceCandleResult(
                False, (), (), sequence_result.reason or "SEQUENCE_UNSAFE"
            )

        integration = SequenceAwareCandleIngestionV1(
            sequence_contract_verified=self.sequence_contract_verified,
            sequence_contract_evidence_ref=self.sequence_contract_evidence_ref,
        )
        try:
            result = integration.ingest(records, as_of=as_of)
        except (TypeError, ValueError):
            return CleanEvidenceCandleResult(False, (), (), "INVALID_FORWARD_INPUT")

        if not result.safe_for_decision:
            return CleanEvidenceCandleResult(
                False, (), (), "SEQUENCE_UNSAFE"
            )
        return CleanEvidenceCandleResult(
            True, tuple(result.candles), tuple(result.gaps), "CANDLE_SAFE"
        )
