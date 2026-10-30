"""Capability-gated boundary from verified ordered trade events to candles."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from .candle_normalizer_v1 import Candle15m, IntervalGap
from .forward_tabdeal_ingestion_v1 import ingest_closed_candles
from .sequence_semantics_v1 import (
    SequenceCapabilitiesV1,
    SequenceEventV2,
    SequenceIntegrityV2,
)


class SequenceCandleResult:
    def __init__(
        self,
        candles: tuple[Candle15m, ...],
        gaps: tuple[IntervalGap, ...],
        events: tuple[SequenceEventV2, ...],
    ) -> None:
        self.candles = candles
        self.gaps = gaps
        self.events = events

    @property
    def safe_for_decision(self) -> bool:
        return not any(
            event.status in {"BLOCKED", "REJECT_STREAM", "ANOMALY"}
            for event in self.events
        )


class SequenceAwareCandleIngestionV1:
    """Only a registry-verified scalar sequence may gate this legacy trade path."""

    def __init__(
        self,
        *,
        capabilities: SequenceCapabilitiesV1 | None = None,
        max_sequence_records: int = 100_000,
    ) -> None:
        self.sequence = SequenceIntegrityV2(
            capabilities, max_records=max_sequence_records
        )

    def ingest(
        self,
        records: Iterable[dict[str, Any]],
        *,
        as_of: datetime,
    ) -> SequenceCandleResult:
        safe: list[dict[str, Any]] = []
        events: list[SequenceEventV2] = []

        for record in records:
            event = self.sequence.observe(record)
            events.append(event)
            if event.status == "ACCEPTED":
                safe.append(record)
            elif event.status == "IDEMPOTENT_DUPLICATE":
                continue
            else:
                return SequenceCandleResult((), (), tuple(events))

        candles, gaps = ingest_closed_candles(safe, as_of=as_of)
        return SequenceCandleResult(candles, gaps, tuple(events))
