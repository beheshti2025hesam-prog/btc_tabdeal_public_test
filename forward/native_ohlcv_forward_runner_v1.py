"""Disabled-by-default native OHLCV forward runner; independent of trade.sequence."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .forward_observation_writer_v1 import ForwardObservationWriterV1
from .native_ohlcv_v1 import INTERVAL_MS, NativeOHLCVBatch, NativeOHLCVSource
from .runtime_guard_v1 import RuntimeContext

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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


def _validate_batch(batch: NativeOHLCVBatch) -> None:
    for key in ("venue", "product", "symbol", "interval", "endpoint_kind"):
        if not isinstance(getattr(batch, key, None), str) or not getattr(batch, key).strip():
            raise ValueError("missing batch metadata: " + key)
    if batch.interval not in INTERVAL_MS:
        raise ValueError("unsupported fixed interval")
    if type(batch.fetched_at_ms) is not int or batch.fetched_at_ms < 0:
        raise ValueError("invalid fetched_at_ms")
    if type(batch.open_candles_excluded) is not int or batch.open_candles_excluded < 0:
        raise ValueError("invalid open_candles_excluded")
    if not isinstance(batch.response_sha256, str) or not _SHA256.fullmatch(batch.response_sha256):
        raise ValueError("invalid response SHA-256")

    interval_ms = INTERVAL_MS[batch.interval]
    previous_open = None
    seen = set()
    for candle in batch.candles:
        if (candle.venue, candle.product, candle.symbol, candle.interval) != (
            batch.venue, batch.product, batch.symbol, batch.interval
        ):
            raise ValueError("candle source scope differs from batch")
        if type(candle.closed) is not bool or candle.closed is not True:
            raise ValueError("unclosed candle in native batch")
        if type(candle.open_time_ms) is not int or type(candle.close_time_ms) is not int:
            raise ValueError("candle timestamps must be integers")
        if candle.open_time_ms < 0 or candle.close_time_ms != candle.open_time_ms + interval_ms - 1:
            raise ValueError("invalid candle timestamps")
        if candle.open_time_ms % interval_ms or candle.close_time_ms >= batch.fetched_at_ms:
            raise ValueError("unclosed or misaligned candle")
        if candle.open_time_ms in seen or (
            previous_open is not None and candle.open_time_ms <= previous_open
        ):
            raise ValueError("duplicate or unordered candle")
        seen.add(candle.open_time_ms)
        previous_open = candle.open_time_ms
        prices = (candle.open, candle.high, candle.low, candle.close)
        if any(type(x) is not Decimal or not x.is_finite() or x <= 0 for x in prices):
            raise ValueError("invalid OHLC decimal")
        if candle.high < max(candle.open, candle.low, candle.close):
            raise ValueError("invalid candle high")
        if candle.low > min(candle.open, candle.high, candle.close):
            raise ValueError("invalid candle low")
        if any(type(x) is not Decimal or not x.is_finite() or x < 0
               for x in (candle.volume, candle.quote_volume)):
            raise ValueError("invalid volume")
        if type(candle.trade_count) is not int or candle.trade_count < 0:
            raise ValueError("invalid trade count")
    for gap in batch.gaps:
        if type(gap.missing_intervals) is not int or gap.missing_intervals <= 0:
            raise ValueError("invalid gap count")
        if type(gap.expected_open_time_ms) is not int or type(gap.next_observed_open_time_ms) is not int:
            raise ValueError("invalid gap timestamps")
        if gap.next_observed_open_time_ms <= gap.expected_open_time_ms:
            raise ValueError("invalid gap boundaries")


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
            _validate_batch(batch)
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
