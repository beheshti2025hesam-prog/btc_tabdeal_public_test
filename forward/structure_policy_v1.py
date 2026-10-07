"""Explicit causal swing confirmation for Structure Policy v1.

Only closed candles are used. A pivot is attributed to its own candle but is
confirmed only after two subsequent closed candles exist.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from .candle_normalizer_v1 import Candle15m
from .market_structure_v1 import SwingPoint, classify_swing_labels

RIGHT_CANDLES = 2
TIMEFRAME_DELTA = timedelta(minutes=15)


def confirm_swings_v1(
    candles: Sequence[Candle15m],
    *,
    observed_at: datetime,
) -> tuple[SwingPoint, ...]:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    observed_at = observed_at.astimezone(timezone.utc)

    ordered = sorted(candles, key=lambda c: c.open_time)
    if not ordered:
        return ()

    symbol = ordered[0].symbol
    for candle in ordered:
        if candle.symbol != symbol:
            raise ValueError("mixed symbols are not allowed")
        if candle.timeframe != "15m":
            raise ValueError("only 15m candles are supported")
        if candle.close_time > observed_at:
            raise ValueError("candle occurs after observed_at")

    points: list[SwingPoint] = []
    for i in range(RIGHT_CANDLES, len(ordered) - RIGHT_CANDLES):
        window = ordered[i - RIGHT_CANDLES : i + RIGHT_CANDLES + 1]
        pivot = ordered[i]

        expected = window[0].open_time
        if any(c.open_time != expected + j * TIMEFRAME_DELTA for j, c in enumerate(window)):
            continue

        if pivot.close_time + RIGHT_CANDLES * TIMEFRAME_DELTA > observed_at:
            continue

        left = window[:RIGHT_CANDLES]
        right = window[RIGHT_CANDLES + 1 :]

        if all(pivot.high > c.high for c in (*left, *right)):
            points.append(SwingPoint("SWING_HIGH", pivot.high, pivot.close_time, pivot.last_sequence))

        if all(pivot.low < c.low for c in (*left, *right)):
            points.append(SwingPoint("SWING_LOW", pivot.low, pivot.close_time, pivot.last_sequence))

    return tuple(sorted(points, key=lambda p: (p.candle_time, p.kind)))


def label_confirmed_swings_v1(swings: Sequence[SwingPoint]) -> tuple[tuple[SwingPoint, str], ...]:
    result: list[tuple[SwingPoint, str]] = []
    history: list[SwingPoint] = []
    for swing in sorted(swings, key=lambda p: (p.candle_time, p.kind)):
        labels = classify_swing_labels(history, swing)
        result.append((swing, labels[0] if labels else "UNCLASSIFIED"))
        history.append(swing)
    return tuple(result)
