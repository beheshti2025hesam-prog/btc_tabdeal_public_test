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
    """Build deterministic closed candles and explicit missing intervals.

    as_of is mandatory so an open 15m bucket can never be emitted as closed.
    expected_symbol prevents accidental multi-symbol aggregation.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    as_of = as_of.astimezone(timezone.utc)

    unique: dict[int, TradeObservation] = {}
    symbol = expected_symbol

    for trade in trades:
        if trade.updated.tzinfo is None:
            raise ValueError("updated must be timezone-aware")
        updated = trade.updated.astimezone(timezone.utc)
        if updated > as_of:
            raise ValueError("observation occurs after as_of")
        if trade.price <= 0 or trade.amount < 0:
            raise ValueError("price must be > 0 and amount must be >= 0")

        if symbol is None:
            symbol = trade.symbol
        if trade.symbol != symbol:
            raise ValueError(
                f"mixed symbols are not allowed: expected {symbol}, got {trade.symbol}"
            )

        if trade.sequence in unique:
            if unique[trade.sequence] != trade:
                raise ValueError(f"Conflicting duplicate sequence: {trade.sequence}")
            continue
        unique[trade.sequence] = trade

    ordered = sorted(
        unique.values(),
        key=lambda x: (x.updated.astimezone(timezone.utc), x.sequence),
    )
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
        rows = buckets.get(cursor)
        if not rows:
            gaps.append(
                IntervalGap(
                    symbol=symbol or "",
                    timeframe=TIMEFRAME,
                    open_time=cursor,
                    close_time=close_time,
                )
            )
        else:
            rows = sorted(
                rows,
                key=lambda x: (x.updated.astimezone(timezone.utc), x.sequence),
            )
            prices = [x.price for x in rows]
            candles.append(
                Candle15m(
                    symbol=symbol or rows[0].symbol,
                    timeframe=TIMEFRAME,
                    open_time=cursor,
                    close_time=close_time,
                    open=rows[0].price,
                    high=max(prices),
                    low=min(prices),
                    close=rows[-1].price,
                    volume=sum((x.amount for x in rows), Decimal("0")),
                    trade_count=len(rows),
                    first_sequence=rows[0].sequence,
                    last_sequence=rows[-1].sequence,
                    source_first_observed_at=rows[0].updated.astimezone(timezone.utc),
                    source_last_observed_at=rows[-1].updated.astimezone(timezone.utc),
                )
            )
        cursor = close_time

    return tuple(candles), tuple(gaps)
