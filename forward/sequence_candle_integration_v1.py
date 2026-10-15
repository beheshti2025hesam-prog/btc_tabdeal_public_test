"""Boundary from fresh Tabdeal trades to closed 15m candles."""
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
    """Do not use an opaque sequence value as identity, order, or conflict key."""

    def __init__(
        self, *, max_sequence_records: int = 100_000,
        sequence_ordering_authorized: bool = False,
    ) -> None:
        if type(sequence_ordering_authorized) is not bool:
            raise ValueError("sequence_ordering_authorized must be bool")
        self.sequence_ordering_authorized = sequence_ordering_authorized
        self.sequence = SequenceIntegrityV1(max_records=max_sequence_records, sequence_semantics_verified=False)

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
            elif event.status == "EXACT_REPLAY":
                continue
            else:
                return SequenceCandleResult((), (), tuple(events))

        # Candle normalization must not infer identity or ordering from sequence.
        # It raises on same-timestamp ambiguity instead of manufacturing an order.
        try:
            candles, gaps = ingest_closed_candles(
                safe, as_of=as_of,
                sequence_ordering_authorized=self.sequence_ordering_authorized,
            )
        except ValueError as exc:
            if "ambiguous timestamp tie" in str(exc):
                events.append(SequenceEvent(
                    sequence=-1,
                    status="REJECT_STREAM",
                    reason="AMBIGUOUS_TIMESTAMP_ORDER",
                ))
                return SequenceCandleResult((), (), tuple(events))
            raise
        return SequenceCandleResult(candles, gaps, tuple(events))
