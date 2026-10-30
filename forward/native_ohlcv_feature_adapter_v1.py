"""Bridge validated native OHLCV batches into existing candle-based features.

The source batch remains the precision-preserving authority. The existing
feature calculators consume float-based core.data_engine.candles.Candle, so
conversion occurs only at this explicit analytics boundary. Provenance and
the original source digest stay attached to the returned envelope.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from core.data_engine.candles import Candle
from .native_ohlcv_v1 import INTERVAL_MS, CandleGap, NativeOHLCVBatch, validate_native_batch


@dataclass(frozen=True)
class NativeOHLCVFeatureBatch:
    venue: str
    product: str
    symbol: str
    interval: str
    timeframe_seconds: int
    fetched_at_ms: int
    as_of_ms: int
    source_response_sha256: str
    candles: tuple[Candle, ...]
    gaps: tuple[CandleGap, ...]
    source_candle_count: int
    as_of_candles_excluded: int
    open_candles_excluded: int


def to_feature_batch(
    batch: NativeOHLCVBatch,
    *,
    as_of_ms: int | None = None,
    now_ms: int | None = None,
) -> NativeOHLCVFeatureBatch:
    """Convert closed native candles for analytics without using trade-derived candles."""
    validate_native_batch(batch)
    observed_now = int(time.time() * 1000) if now_ms is None else now_ms
    if type(observed_now) is not int or observed_now < 0:
        raise ValueError("now_ms must be a non-negative integer")
    if batch.fetched_at_ms > observed_now + 60_000:
        raise ValueError("native batch fetch timestamp is in the future")

    cutoff = batch.fetched_at_ms if as_of_ms is None else as_of_ms
    if type(cutoff) is not int or cutoff < 0:
        raise ValueError("as_of_ms must be a non-negative integer")
    if cutoff > batch.fetched_at_ms:
        raise ValueError("as_of_ms must not be after the source fetch time")

    timeframe_seconds = INTERVAL_MS[batch.interval] // 1000
    eligible = tuple(c for c in batch.candles if c.close_time_ms < cutoff)
    excluded = len(batch.candles) - len(eligible)
    candles: list[Candle] = []
    for native in eligible:
        values = tuple(float(value) for value in (
            native.open, native.high, native.low, native.close, native.volume
        ))
        if not all(math.isfinite(value) for value in values):
            raise ValueError("native candle cannot be represented as finite analytics floats")
        start = datetime.fromtimestamp(native.open_time_ms / 1000, tz=timezone.utc)
        # The core Candle.end is exclusive; native close_time_ms is inclusive.
        end = datetime.fromtimestamp((native.close_time_ms + 1) / 1000, tz=timezone.utc)
        candles.append(Candle(
            symbol=native.symbol,
            timeframe_seconds=timeframe_seconds,
            start=start,
            end=end,
            open=values[0],
            high=values[1],
            low=values[2],
            close=values[3],
            volume=values[4],
            trade_count=native.trade_count,
        ))

    last_selected_open = eligible[-1].open_time_ms if eligible else None
    gaps = tuple(
        gap for gap in batch.gaps
        if last_selected_open is not None
        and gap.next_observed_open_time_ms <= last_selected_open
    )
    return NativeOHLCVFeatureBatch(
        venue=batch.venue,
        product=batch.product,
        symbol=batch.symbol,
        interval=batch.interval,
        timeframe_seconds=timeframe_seconds,
        fetched_at_ms=batch.fetched_at_ms,
        as_of_ms=cutoff,
        source_response_sha256=batch.response_sha256,
        candles=tuple(candles),
        gaps=gaps,
        source_candle_count=len(batch.candles),
        as_of_candles_excluded=excluded,
        open_candles_excluded=batch.open_candles_excluded,
    )
