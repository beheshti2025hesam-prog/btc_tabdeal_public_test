"""Deterministic 15-minute candle normalization contract.

Consumes fresh raw trade observations and emits only closed candles.
No strategy, indicator, threshold, signal, or outcome logic belongs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

TIMEFRAME = "15m"


@dataclass(frozen=True)
class TradeObservation:
    symbol: str
    price: Decimal
    amount: Decimal
    side: str
    updated: datetime
    sequence: int


@dataclass(frozen=True)
class Candle15m:
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trade_count: int
    first_sequence: int
    last_sequence: int
    source_first_observed_at: datetime
    source_last_observed_at: datetime


@dataclass(frozen=True)
class IntervalGap:
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    reason: str = "NO_SOURCE_OBSERVATIONS"


def floor_15m(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    value = value.astimezone(timezone.utc)
    minute = (value.minute // 15) * 15
    return value.replace(minute=minute, second=0, microsecond=0)


def normalize_trades(
    trades: Iterable[TradeObservation],
    *,
    as_of: datetime,
    expected_symbol: str | None = None,
) -> tuple[tuple[Candle15m, ...], tuple[IntervalGap, ...]]:
    """Build closed candles; timestamps order events, never opaque sequence IDs.

    When multiple distinct prices have the exact same source timestamp, the
    OHLC open/close ordering is not established by timestamps. Without an
    authorized ordering capability, fail closed rather than using sequence as
    a tie-breaker. Repeated sequence values are not deduplicated or conflicted.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    as_of = as_of.astimezone(timezone.utc)

    rows: list[TradeObservation] = []
    symbol = expected_symbol
    for trade in trades:
        if trade.updated.tzinfo is None or trade.updated.utcoffset() is None:
            raise ValueError("updated must be timezone-aware")
        updated = trade.updated.astimezone(timezone.utc)
        if updated > as_of:
            raise ValueError("observation occurs after as_of")
        if trade.price <= 0 or trade.amount < 0:
            raise ValueError("price must be > 0 and amount must be >= 0")
        if symbol is None:
            symbol = trade.symbol
        if trade.symbol != symbol:
            raise ValueError(f"mixed symbols are not allowed: expected {symbol}, got {trade.symbol}")
        rows.append(trade)

    # Python's stable sort preserves observed input order for equal timestamps,
    # but that arrival order is not evidence of venue order; reject ambiguous ties.
    ordered = sorted(rows, key=lambda x: x.updated.astimezone(timezone.utc))
    for previous, current in zip(ordered, ordered[1:]):
        if (
            previous.updated.astimezone(timezone.utc) == current.updated.astimezone(timezone.utc)
            and previous.price != current.price
        ):
            raise ValueError("ambiguous timestamp tie without verified ordering")

    if not ordered:
        return (), ()

    buckets: dict[datetime, list[TradeObservation]] = {}
    for trade in ordered:
        bucket = floor_15m(trade.updated)
        if bucket + timedelta(minutes=15) <= as_of:
            buckets.setdefault(bucket, []).append(trade)

    if not buckets:
        return (), ()

    candles: list[Candle15m] = []
    gaps: list[IntervalGap] = []
    cursor = min(buckets)
    last_bucket = max(buckets)

    while cursor <= last_bucket:
        close_time = cursor + timedelta(minutes=15)
        bucket_rows = buckets.get(cursor)
        if not bucket_rows:
            gaps.append(IntervalGap(
                symbol=symbol or "", timeframe=TIMEFRAME,
                open_time=cursor, close_time=close_time,
            ))
        else:
            prices = [x.price for x in bucket_rows]
            candles.append(Candle15m(
                symbol=symbol or bucket_rows[0].symbol,
                timeframe=TIMEFRAME,
                open_time=cursor,
                close_time=close_time,
                open=bucket_rows[0].price,
                high=max(prices),
                low=min(prices),
                close=bucket_rows[-1].price,
                volume=sum((x.amount for x in bucket_rows), Decimal("0")),
                trade_count=len(bucket_rows),
                first_sequence=bucket_rows[0].sequence,
                last_sequence=bucket_rows[-1].sequence,
                source_first_observed_at=bucket_rows[0].updated.astimezone(timezone.utc),
                source_last_observed_at=bucket_rows[-1].updated.astimezone(timezone.utc),
            ))
        cursor = close_time

    return tuple(candles), tuple(gaps)
