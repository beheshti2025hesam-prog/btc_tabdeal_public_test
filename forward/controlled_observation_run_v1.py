"""Controlled forward observation run: fresh records in, NO_TRADE observations out.

No network and no execution. The caller supplies only contemporaneous Tabdeal
records; this runner validates the time boundary, normalizes closed 15m candles,
and writes immutable observation artifacts.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Iterable

from .forward_tabdeal_ingestion_v1 import ingest_closed_candles
from .forward_observation_writer_v1 import ForwardObservationWriterV1
from .runtime_guard_v1 import RuntimeContext


class ControlledObservationRunV1:
    def __init__(self, *, writer: ForwardObservationWriterV1):
        self.writer = writer

    def run(self, *, forward_run_id: str, observed_at: datetime,
            records: Iterable[dict[str, Any]]) -> tuple[str, ...]:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        observed_at = observed_at.astimezone(timezone.utc)
        materialized = tuple(records)
        candles, gaps = ingest_closed_candles(materialized, as_of=observed_at)
        context = RuntimeContext(
            source="tabdeal_ws_forward_v1",
            observed_at=observed_at.isoformat(),
            forward_run_id=forward_run_id,
        )
        digests: list[str] = []
        for candle in candles:
            event_id = f"{forward_run_id}:candle:{candle.open_time.isoformat()}"
            digests.append(self.writer.append({
                "event_id": event_id,
                "observed_at": observed_at.isoformat(),
                "symbol": candle.symbol,
                "timeframe": candle.timeframe,
                "status": "CANDLE_CLOSED_OBSERVED",
                "source": "tabdeal_ws_forward_v1",
                "open_time": candle.open_time.isoformat(),
                "close_time": candle.close_time.isoformat(),
                "first_sequence": candle.first_sequence,
                "last_sequence": candle.last_sequence,
                "trade_count": candle.trade_count,
            }, context=context))
        for gap in gaps:
            event_id = f"{forward_run_id}:gap:{gap.open_time.isoformat()}"
            digests.append(self.writer.append({
                "event_id": event_id,
                "observed_at": observed_at.isoformat(),
                "symbol": gap.symbol,
                "timeframe": gap.timeframe,
                "status": "NO_TRADE_DATA_GAP",
                "source": "tabdeal_ws_forward_v1",
                "open_time": gap.open_time.isoformat(),
                "close_time": gap.close_time.isoformat(),
                "reason": gap.reason,
            }, context=context))
        return tuple(digests)
