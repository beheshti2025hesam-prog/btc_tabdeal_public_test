"""A single, fail-closed boundary from native venue OHLCV into HES features.

This module does not fetch data, aggregate trades, infer sequence semantics, or
execute trades. Venue adapters remain responsible for transport and evidence.
Decimal values are retained until the explicit legacy feature-engine boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Iterable

from core.data_engine.candles import Candle


@dataclass(frozen=True)
class NativeMarketIdentity:
    venue: str
    market: str
    symbol: str
    timeframe_seconds: int
    source: str


@dataclass(frozen=True)
class NativeCandleRecord:
    start: datetime
    end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class NativeCandleGap:
    expected_start: datetime
    observed_start: datetime


@dataclass(frozen=True)
class NativeCandleBatch:
    identity: NativeMarketIdentity
    candles: tuple[NativeCandleRecord, ...]
    gaps: tuple[NativeCandleGap, ...]
    discarded_open_candles: int


def _aware_utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def _decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"invalid_{name}")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid_{name}") from exc
    if not result.is_finite():
        raise ValueError(f"invalid_{name}")
    return result


def _read_time(candle: Any, datetime_name: str, millis_name: str, fallback_name: str) -> datetime:
    value = getattr(candle, datetime_name, None)
    if value is None:
        value = getattr(candle, fallback_name, None)
    if value is not None:
        return _aware_utc(value, datetime_name)
    millis = getattr(candle, millis_name, None)
    if isinstance(millis, bool) or not isinstance(millis, int):
        raise ValueError(f"missing_or_invalid_{datetime_name}")
    try:
        return datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError) as exc:
        raise ValueError(f"invalid_{datetime_name}") from exc


def _timeframe_seconds(candle: Any) -> int:
    seconds = getattr(candle, "timeframe_seconds", None)
    if seconds is not None:
        if isinstance(seconds, bool) or not isinstance(seconds, int):
            raise ValueError("invalid_timeframe")
        result = seconds
    else:
        minutes = getattr(candle, "timeframe_minutes", None)
        if minutes is not None:
            if isinstance(minutes, bool) or not isinstance(minutes, int):
                raise ValueError("invalid_timeframe")
            result = minutes * 60
        else:
            interval = getattr(candle, "interval", None)
            if not isinstance(interval, str) or not interval:
                raise ValueError("missing_timeframe")
            units = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
            suffix = interval[-1]
            if suffix not in units or not interval[:-1].isdigit():
                raise ValueError("unsupported_timeframe")
            result = int(interval[:-1]) * units[suffix]
    if result <= 0:
        raise ValueError("invalid_timeframe")
    return result


def normalize_native_candles(
    candles: Iterable[Any], *, venue: str, market: str, as_of: datetime,
    source: str | None = None,
) -> NativeCandleBatch:
    """Normalize one existing adapter's batch; no trade sequence is required."""
    if not venue.strip() or not market.strip():
        raise ValueError("venue_and_market_required")
    cutoff = _aware_utc(as_of, "as_of")
    rows = tuple(candles)
    if not rows:
        raise ValueError("empty_native_candle_batch")

    first = rows[0]
    symbol = getattr(first, "symbol", None)
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("missing_symbol")
    timeframe = _timeframe_seconds(first)
    inferred_source = source or getattr(first, "source", None) or f"{venue}_native_ohlcv"
    identity = NativeMarketIdentity(venue.strip().lower(), market.strip().lower(),
                                    symbol.strip(), timeframe, str(inferred_source))
    # The pinned Wallex UDF-history adapter emits no per-row market field and is
    # the Spot chart path. Never let caller-supplied identity relabel it as Futures.
    adapter_source = getattr(first, "source", None)
    if adapter_source == "wallex_native_udf_history" and (
        identity.venue != "wallex" or identity.market != "spot"
    ):
        raise ValueError("source_market_mismatch")

    normalized: list[NativeCandleRecord] = []
    discarded_open = 0
    seen: set[datetime] = set()
    previous_start: datetime | None = None
    for row in rows:
        if getattr(row, "symbol", None) != identity.symbol or _timeframe_seconds(row) != timeframe:
            raise ValueError("mixed_symbol_or_timeframe")
        row_market = getattr(row, "market", None)
        if row_market is not None and str(row_market).strip().lower() != identity.market:
            raise ValueError("mixed_market")
        row_source = getattr(row, "source", None)
        if row_source is not None and str(row_source) != identity.source:
            raise ValueError("mixed_source")
        start = _read_time(row, "open_time", "open_time_ms", "start")
        end = _read_time(row, "close_time", "close_time_ms", "end")
        if end <= start:
            raise ValueError("invalid_candle_bounds")
        # Wallex uses an exclusive close boundary; Binance's close_time_ms is
        # the final millisecond inside the candle. Canonicalize both to an
        # exclusive end boundary after validating the adapter representation.
        millis_close = getattr(row, "close_time_ms", None)
        exclusive_end = start + timedelta(seconds=timeframe)
        if millis_close is not None:
            if end != exclusive_end - timedelta(milliseconds=1):
                raise ValueError("candle_duration_mismatch")
        elif end != exclusive_end:
            raise ValueError("candle_duration_mismatch")
        if start in seen:
            raise ValueError("duplicate_candle_open_time")
        if previous_start is not None and start <= previous_start:
            raise ValueError("candles_not_strictly_ordered")
        seen.add(start)
        previous_start = start
        explicitly_closed = getattr(row, "is_closed", None)
        if explicitly_closed is False or end > cutoff or (explicitly_closed is None and end >= cutoff):
            discarded_open += 1
            continue
        op = _decimal(getattr(row, "open", None), "open")
        high = _decimal(getattr(row, "high", None), "high")
        low = _decimal(getattr(row, "low", None), "low")
        close = _decimal(getattr(row, "close", None), "close")
        volume = _decimal(getattr(row, "volume", None), "volume")
        if min(op, high, low, close) <= 0 or volume < 0:
            raise ValueError("nonpositive_ohlc_or_negative_volume")
        if high < max(op, close, low) or low > min(op, close, high):
            raise ValueError("invalid_ohlc_range")
        normalized.append(NativeCandleRecord(start, exclusive_end, op, high, low, close, volume))

    if not normalized:
        raise ValueError("no_fully_closed_candles")
    gaps: list[NativeCandleGap] = []
    step = timeframe
    for previous, current in zip(normalized, normalized[1:]):
        expected = previous.start.timestamp() + step
        observed = current.start.timestamp()
        if observed - expected > 0.5:
            gaps.append(NativeCandleGap(
                datetime.fromtimestamp(expected, tz=timezone.utc), current.start
            ))
    return NativeCandleBatch(identity, tuple(normalized), tuple(gaps), discarded_open)


def to_feature_candles(
    batch: NativeCandleBatch, *, include_volume: bool = False
) -> tuple[Candle, ...]:
    """Convert Decimal OHLC into the existing feature engine's float contract.

    Volume is omitted by default because source semantics may be unverified.
    Wallex UDF volume is fail-closed even when explicitly requested. The
    original Decimal volume remains available in the source batch for evidence.
    """
    if not isinstance(include_volume, bool):
        raise ValueError("include_volume_must_be_boolean")
    identity = batch.identity
    if include_volume and (
        identity.venue.lower() == "wallex"
        or "wallex" in identity.source.lower()
    ):
        raise ValueError("wallex_volume_semantics_unresolved")

    result: list[Candle] = []
    for row in batch.candles:
        ohlc = tuple(float(v) for v in (row.open, row.high, row.low, row.close))
        if not all(isfinite(value) for value in ohlc):
            raise ValueError("feature_float_conversion_not_finite")
        volume: float | None = None
        if include_volume:
            volume = float(row.volume)
            if not isfinite(volume) or volume < 0:
                raise ValueError("feature_volume_conversion_invalid")
        result.append(Candle(
            symbol=identity.symbol,
            timeframe_seconds=identity.timeframe_seconds,
            start=row.start, end=row.end,
            open=ohlc[0], high=ohlc[1], low=ohlc[2],
            close=ohlc[3], volume=volume, trade_count=None,
        ))
    return tuple(result)
