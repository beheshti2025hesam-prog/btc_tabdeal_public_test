"""Disabled-by-default native OHLCV forward runner; independent of trade.sequence."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .forward_observation_writer_v1 import ForwardObservationWriterV1
from .native_ohlcv_v1 import INTERVAL_MS, NativeOHLCVBatch, NativeOHLCVSource, validate_native_batch
from .runtime_guard_v1 import RuntimeContext


@dataclass(frozen=True)
class NativeOHLCVForwardRunResult:
    run_id: str
    status: str
    journal_path: str
    reason: str
    candle_count: int = 0
    gap_count: int = 0
    journal_digest: str | None = None
    response_sha256: str | None = None


class NativeOHLCVForwardRunnerV1:
    """One bounded native-candle fetch and one immutable journal record."""

    def __init__(self, *, source: NativeOHLCVSource, journal_path: str | Path,
                 enabled: bool = False, writer: ForwardObservationWriterV1 | None = None):
        if type(enabled) is not bool:
            raise ValueError("enabled must be bool")
        self.source = source
        self.journal_path = Path(journal_path)
        self.enabled = enabled
        self.writer = writer or ForwardObservationWriterV1(self.journal_path)

    def run_once(self, *, symbol: str, interval: str = "15m", limit: int = 100,
                 start_time_ms: int | None = None, end_time_ms: int | None = None,
                 run_id: str | None = None) -> NativeOHLCVForwardRunResult:
        run_id = run_id or ("native-" + uuid.uuid4().hex)
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be non-empty")
        if not self.enabled:
            return NativeOHLCVForwardRunResult(
                run_id, "BLOCKED", str(self.journal_path), "NATIVE_OHLCV_RUNNER_DISABLED"
            )
        if not isinstance(symbol, str) or not symbol.strip() or interval not in INTERVAL_MS:
            raise ValueError("invalid symbol or interval")
        try:
            batch = self.source.fetch(
                symbol=symbol, interval=interval, limit=limit,
                start_time_ms=start_time_ms, end_time_ms=end_time_ms,
            )
            validate_native_batch(batch)
            if batch.fetched_at_ms > int(datetime.now(timezone.utc).timestamp() * 1000) + 60_000:
                raise ValueError("fetch timestamp is in the future")
            if batch.symbol != symbol or batch.interval != interval:
                raise ValueError("response scope differs from request")
        except Exception as exc:
            return NativeOHLCVForwardRunResult(
                run_id, "BLOCKED", str(self.journal_path),
                f"NATIVE_OHLCV_SOURCE_INVALID:{type(exc).__name__}",
            )

        observed_at = datetime.fromtimestamp(batch.fetched_at_ms / 1000, tz=timezone.utc)
        source_name = f"{batch.venue}_native_ohlcv_v1"
        record = {
            "event_id": f"{run_id}:batch:{batch.fetched_at_ms}",
            "observed_at": observed_at.isoformat(),
            "symbol": batch.symbol,
            "timeframe": batch.interval,
            "status": ("NATIVE_OHLCV_GAPS_PRESENT" if batch.gaps else
                       "NATIVE_OHLCV_BATCH_OBSERVED" if batch.candles else
                       "NATIVE_OHLCV_NO_CLOSED_CANDLES"),
            "source": source_name,
            "venue": batch.venue,
            "product": batch.product,
            "endpoint_kind": batch.endpoint_kind,
            "fetched_at_ms": batch.fetched_at_ms,
            "source_response_sha256": batch.response_sha256,
            "open_candles_excluded": batch.open_candles_excluded,
            "candles": [{
                "open_time_ms": c.open_time_ms, "close_time_ms": c.close_time_ms,
                "open": str(c.open), "high": str(c.high), "low": str(c.low),
                "close": str(c.close), "volume": str(c.volume),
                "quote_volume": str(c.quote_volume), "trade_count": c.trade_count,
            } for c in batch.candles],
            "gaps": [{
                "expected_open_time_ms": g.expected_open_time_ms,
                "next_observed_open_time_ms": g.next_observed_open_time_ms,
                "missing_intervals": g.missing_intervals,
            } for g in batch.gaps],
            "execution": "OFF",
        }
        context = RuntimeContext(source_name, observed_at.isoformat(), run_id)
        try:
            digest = self.writer.append(record, context=context)
        except Exception as exc:
            return NativeOHLCVForwardRunResult(
                run_id, "BLOCKED", str(self.journal_path),
                f"NATIVE_OHLCV_JOURNAL_WRITE_FAILED:{type(exc).__name__}",
                len(batch.candles), len(batch.gaps), None, batch.response_sha256,
            )
        return NativeOHLCVForwardRunResult(
            run_id, record["status"], str(self.journal_path), "NATIVE_OHLCV_BATCH_RECORDED",
            len(batch.candles), len(batch.gaps), digest, batch.response_sha256,
        )
