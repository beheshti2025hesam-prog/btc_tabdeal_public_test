"""Sequence-aware boundary from fresh Tabdeal trades to closed 15m candles."""
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
    ) -> None:
        self.candles = candles
        self.gaps = gaps
        self.events = events

    @property
    def safe_for_decision(self) -> bool:
        return not any(
            event.status in {"REJECT_STREAM", "ANOMALY"} for event in self.events
        )


class SequenceAwareCandleIngestionV1:
    """Sequence-check first; candle normalization only receives safe records."""

    def __init__(self) -> None:
        self.sequence = SequenceIntegrityV1()

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
            elif event.status == "IDEMPOTENT_DUPLICATE":
                continue
            else:
                # Never feed an ambiguous stream into candle formation.
                return SequenceCandleResult((), (), tuple(events))

        candles, gaps = ingest_closed_candles(safe, as_of=as_of)
        return SequenceCandleResult(candles, gaps, tuple(events))
