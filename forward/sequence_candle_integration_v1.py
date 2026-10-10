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
    ) -> None:
        self.candles = candles
        self.gaps = gaps
        self.events = events
        self.source_completeness_verified = source_completeness_verified

    @property
    def safe_for_decision(self) -> bool:
        return self.source_completeness_verified and not any(
            event.status in {"REJECT_STREAM", "ANOMALY"} for event in self.events
        )


class SequenceAwareCandleIngestionV1:
    """Never infer completeness from sequence gaps or monotonicity."""

    def __init__(
        self,
        *,
        max_sequence_records: int = 100_000,
        source_completeness_verified: bool = False,
        source_completeness_evidence_ref: str | None = None,
    ) -> None:
        self.sequence = SequenceIntegrityV1(max_records=max_sequence_records)
        self.source_completeness_verified = bool(
            source_completeness_verified and source_completeness_evidence_ref
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
            event = self.sequence.observe(record)
            events.append(event)
            if event.status == "ACCEPTED":
                safe.append(record)
            else:
                # Never feed an ambiguous stream into candle formation.
                return SequenceCandleResult(
                    (), (), tuple(events),
                    source_completeness_verified=self.source_completeness_verified,
                )

        # The sequence field cannot certify upstream completeness. Without an
        # exact reviewed source contract, do not create a decision-grade candle.
        if not self.source_completeness_verified:
            return SequenceCandleResult(
                (), (), tuple(events), source_completeness_verified=False
            )

        candles, gaps = ingest_closed_candles(safe, as_of=as_of)
        return SequenceCandleResult(
            candles, gaps, tuple(events),
            source_completeness_verified=True,
        )
