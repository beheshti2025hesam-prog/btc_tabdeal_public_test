"""Deterministic 15-minute candle normalization contract.

No strategy, indicator, threshold, signal, or outcome logic belongs here.
The normalizer consumes fresh raw trade observations and produces closed
15-minute candles while preserving source sequence identity.
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
    """Return the UTC 15-minute bucket containing value."""
    if value.tzinfo is None:
        raise ValueError("updated must be timezone-aware")
    value = value.astimezone(timezone.utc)
    minute = (value.minute // 15) * 15
    return value.replace(minute=minute, second=0, microsecond=0)


def normalize_trades(trades: Iterable[TradeObservation]) -> tuple[tuple[Candle15m, ...], tuple[IntervalGap, ...]]:
    """Build deterministic closed-candle candidates from source observations.

    Caller must provide only observations whose timestamps are known to be
    available at evaluation time. This function never fills missing candles.
    """
    unique: dict[int, TradeObservation] = {}

    for trade in trades:
        if trade.updated.tzinfo is None:
            raise ValueError("updated must be timezone-aware")
        if trade.sequence in unique:
            if unique[trade.sequence] != trade:
                raise ValueError(f"Conflicting duplicate sequence: {trade.sequence}")
            continue
        unique[trade.sequence] = trade

    ordered = sorted(unique.values(), key=lambda x: (x.updated, x.sequence))

    if not ordered:
        return (), ()

    buckets: dict[datetime, list[TradeObservation]] = {}
    for trade in ordered:
        buckets.setdefault(floor_15m(trade.updated), []).append(trade)

    candles: list[Candle15m] = []
    cursor = min(buckets)
    last_bucket = max(buckets)

    while cursor <= last_bucket:
        rows = buckets.get(cursor)
        close_time = cursor + timedelta(minutes=15)
        if not rows:
            cursor = close_time
            continue

        rows = sorted(rows, key=lambda x: (x.updated, x.sequence))
        prices = [x.price for x in rows]
        candles.append(
            Candle15m(
                symbol=rows[0].symbol,
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
                source_first_observed_at=rows[0].updated,
                source_last_observed_at=rows[-1].updated,
            )
        )
        cursor = close_time

    return tuple(candles), ()
