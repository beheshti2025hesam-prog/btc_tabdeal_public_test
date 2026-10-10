"""Sequence-aware boundary from fresh trades to closed candles."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from .candle_normalizer_v1 import Candle15m, IntervalGap
from .forward_tabdeal_ingestion_v1 import ingest_closed_candles
from .sequence_integrity_v1 import SequenceEvent, SequenceIntegrityV1


class SequenceCandleResult:
    def __init__(
        self,
        candles: tuple[Candle15m, ...],
        gaps: tuple[IntervalGap, ...],
        events: tuple[SequenceEvent, ...],
        *,
        source_completeness_verified: bool,
        source_ordering_verified: bool,
    ) -> None:
        self.candles = candles
        self.gaps = gaps
        self.events = events
        self.source_completeness_verified = source_completeness_verified
        self.source_ordering_verified = source_ordering_verified

    @property
    def safe_for_decision(self) -> bool:
        return (
            bool(self.events)
            and self.source_completeness_verified
            and self.source_ordering_verified
            and not any(event.status in {"REJECT_STREAM", "ANOMALY"} for event in self.events)
        )


class SequenceAwareCandleIngestionV1:
    """Never infer completeness or ordering from sequence values."""

    def __init__(
        self,
        *,
        max_sequence_records: int = 100_000,
        source_completeness_verified: bool = False,
        source_completeness_evidence_ref: str | None = None,
        source_ordering_verified: bool = False,
        source_ordering_evidence_ref: str | None = None,
    ) -> None:
        self.sequence = SequenceIntegrityV1(max_records=max_sequence_records)
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

    def _blocked(self, events: tuple[SequenceEvent, ...]) -> SequenceCandleResult:
        return SequenceCandleResult(
            (), (), events,
            source_completeness_verified=self.source_completeness_verified,
            source_ordering_verified=self.source_ordering_verified,
        )

    def ingest(
        self,
        records: Iterable[dict[str, Any]],
        *,
        as_of: datetime,
    ) -> SequenceCandleResult:
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

        if not self.source_completeness_verified or not self.source_ordering_verified:
            return self._blocked(tuple(events))

        try:
            candles, gaps = ingest_closed_candles(safe, as_of=as_of)
        except ValueError as exc:
            reason = str(exc)
            if reason not in {
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
        )
