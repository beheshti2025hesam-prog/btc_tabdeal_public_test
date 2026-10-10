"""Sequence-aware boundary from fresh trades to closed candles."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from .candle_normalizer_v1 import Candle15m, IntervalGap
from .forward_tabdeal_ingestion_v1 import ingest_closed_candles
from .sequence_integrity_v1 import SequenceEvent, SequenceIntegrityV1
from .source_evidence_registry_v1 import SourceEvidenceRegistryError, verify_source_evidence_bundle
from pathlib import Path

DEFAULT_SOURCE_EVIDENCE_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "evidence" / "source_evidence_registry_v1.json"


class SequenceCandleResult:
    def __init__(
        self,
        candles: tuple[Candle15m, ...],
        gaps: tuple[IntervalGap, ...],
        events: tuple[SequenceEvent, ...],
        *,
        source_completeness_verified: bool,
        source_ordering_verified: bool,
        sequence_contract_verified: bool = False,
        reason: str | None = None,
    ) -> None:
        self.candles = candles
        self.gaps = gaps
        self.events = events
        self.source_completeness_verified = source_completeness_verified
        self.source_ordering_verified = source_ordering_verified
        self.sequence_contract_verified = sequence_contract_verified
        self.reason = reason

    @property
    def safe_for_decision(self) -> bool:
        return (
            bool(self.events)
            and self.sequence_contract_verified
            and self.source_completeness_verified
            and self.source_ordering_verified
            and self.reason is None
            and not any(event.status in {"REJECT_STREAM", "ANOMALY"} for event in self.events)
        )


class SequenceAwareCandleIngestionV1:
    """Never infer completeness or ordering from sequence values."""

    def __init__(
        self,
        *,
        max_sequence_records: int = 100_000,
        sequence_contract_verified: bool = False,
        sequence_contract_evidence_ref: str | None = None,
        source_completeness_verified: bool = False,
        source_completeness_evidence_ref: str | None = None,
        source_ordering_verified: bool = False,
        source_ordering_evidence_ref: str | None = None,
        source_evidence_registry_path: str | Path | None = None,
    ) -> None:
        self.sequence = SequenceIntegrityV1(max_records=max_sequence_records)
        self.sequence_contract_verified = bool(sequence_contract_verified and isinstance(sequence_contract_evidence_ref, str) and sequence_contract_evidence_ref.strip())
        self.sequence_contract_evidence_ref = sequence_contract_evidence_ref
        self.source_evidence_registry_path = Path(source_evidence_registry_path) if source_evidence_registry_path is not None else DEFAULT_SOURCE_EVIDENCE_REGISTRY_PATH
        self.sequence_contract_evidence_ref = sequence_contract_evidence_ref
        self.source_completeness_evidence_ref = source_completeness_evidence_ref
        self.source_ordering_evidence_ref = source_ordering_evidence_ref
        self.source_completeness_evidence_ref = source_completeness_evidence_ref
        self.source_ordering_evidence_ref = source_ordering_evidence_ref
        self.source_completeness_verified = bool(
            source_completeness_verified
            and isinstance(source_completeness_evidence_ref, str)
            and source_completeness_evidence_ref.strip()
        )
        self.source_ordering_verified = bool(
            source_ordering_verified
            and isinstance(source_ordering_evidence_ref, str)
            and source_ordering_evidence_ref.strip()
        )

    def _blocked(self, events: tuple[SequenceEvent, ...], reason: str | None = None) -> SequenceCandleResult:
        return SequenceCandleResult(
            (), (), events,
            source_completeness_verified=self.source_completeness_verified,
            source_ordering_verified=self.source_ordering_verified,
            sequence_contract_verified=self.sequence_contract_verified,
            reason=reason,
        )

    def ingest(
        self,
        records: Iterable[dict[str, Any]],
        *,
        as_of: datetime,
    ) -> SequenceCandleResult:
        if not self.sequence_contract_verified:
            return self._blocked((), "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED")
        if not self.source_completeness_verified:
            return self._blocked((), "SOURCE_COMPLETENESS_UNVERIFIED")
        if not self.source_ordering_verified:
            return self._blocked((), "SOURCE_ORDERING_UNVERIFIED")
        try:
            verify_source_evidence_bundle(
                self.source_evidence_registry_path,
                sequence_contract_ref=self.sequence_contract_evidence_ref or "",
                source_completeness_ref=self.source_completeness_evidence_ref or "",
                source_ordering_ref=self.source_ordering_evidence_ref or "",
                source_scope="tabdeal-futures:BTC_USDT",
            )
        except SourceEvidenceRegistryError as exc:
            return self._blocked((), exc.code)

        safe: list[dict[str, Any]] = []
        events: list[SequenceEvent] = []

        for record in records:
            try:
                event = self.sequence.observe(record)
            except (TypeError, ValueError):
                return self._blocked(tuple(events))
            events.append(event)
            if event.status == "ACCEPTED":
                safe.append(record)
            else:
                return self._blocked(tuple(events))

        if not events:
            return self._blocked(())

        if not self.source_completeness_verified or not self.source_ordering_verified or not self.sequence_contract_verified:
            return self._blocked(tuple(events))

        try:
            candles, gaps = ingest_closed_candles(safe, as_of=as_of)
        except ValueError as exc:
            reason = str(exc)
            if "future" in reason.lower():
                reason = "INVALID_FORWARD_INPUT"
            elif reason not in {
                "AMBIGUOUS_EQUAL_SOURCE_TIMESTAMP_ORDER",
                "REPEATED_SEQUENCE_IDENTITY_UNPROVEN",
            }:
                reason = "CANDLE_NORMALIZATION_FAILED"
            blocked_event = SequenceEvent(
                self.sequence.last_sequence if self.sequence.last_sequence is not None else "",
                "REJECT_STREAM",
                reason,
            )
            return self._blocked((*events, blocked_event))

        return SequenceCandleResult(
            candles, gaps, tuple(events),
            source_completeness_verified=True,
            source_ordering_verified=True,
            sequence_contract_verified=True,
        )
