"""Capability-gated boundary from Tabdeal trades to closed 15m candles."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Iterable
from .candle_normalizer_v1 import Candle15m, IntervalGap
from .forward_tabdeal_ingestion_v1 import ingest_closed_candles
from .sequence_integrity_v1 import SequenceEvent, SequenceIntegrityV1
from .tabdeal_sequence_contract_v1 import evaluate_tabdeal_trade_sequence_capabilities


class SequenceCandleResult:
    def __init__(self, candles: tuple[Candle15m, ...], gaps: tuple[IntervalGap, ...],
                 events: tuple[SequenceEvent, ...], reason: str = "SEQUENCE_CAPABILITIES_VERIFIED",
                 diagnostics: tuple[dict[str, Any], ...] = ()) -> None:
        self.candles = candles
        self.gaps = gaps
        self.events = events
        self.reason = reason
        self.diagnostics = diagnostics

    @property
    def safe_for_decision(self) -> bool:
        return self.reason == "SEQUENCE_CAPABILITIES_VERIFIED" and not any(
            event.status in {"REJECT_STREAM", "ANOMALY"} for event in self.events
        )


class SequenceAwareCandleIngestionV1:
    """Use numeric sequence checks only after exact-scope capabilities are proven."""
    def __init__(self, *, max_sequence_records: int = 100_000) -> None:
        self.sequence = SequenceIntegrityV1(max_records=max_sequence_records)

    def ingest(self, records: Iterable[dict[str, Any]], *, as_of: datetime) -> SequenceCandleResult:
        capability_gate = evaluate_tabdeal_trade_sequence_capabilities()
        if not capability_gate["safe"]:
            return SequenceCandleResult((), (), (), capability_gate["reason"], (capability_gate,))
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
                return SequenceCandleResult((), (), tuple(events), event.reason or event.status)
        candles, gaps = ingest_closed_candles(safe, as_of=as_of)
        return SequenceCandleResult(candles, gaps, tuple(events), "SEQUENCE_CAPABILITIES_VERIFIED")
