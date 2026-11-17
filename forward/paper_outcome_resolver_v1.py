"""Shared deterministic 15m paper outcome resolver.

This is the single candle-path resolver used by both the existing Strategy V2
paper evaluator and family-isolated research cohorts. It does not submit orders.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def resolve_paper_outcome(
    candidate: Mapping[str, Any],
    rows_15m: Sequence[Mapping[str, Any]],
    *,
    max_hold_seconds: int = 86_400,
) -> dict[str, Any] | None:
    if not isinstance(candidate, Mapping):
        raise ValueError("PAPER_CANDIDATE_INVALID")
    if type(max_hold_seconds) is not int or max_hold_seconds <= 0:
        raise ValueError("PAPER_MAX_HOLD_INVALID")
    try:
        candidate_time = int(candidate["candidate_time"])
        direction = candidate["direction"]
        stop = float(candidate["stop_loss"])
        target = float(candidate["take_profit"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("PAPER_CANDIDATE_GEOMETRY_INVALID") from exc
    if (candidate_time <= 0 or direction not in ("LONG", "SHORT")
            or stop <= 0 or target <= 0):
        raise ValueError("PAPER_CANDIDATE_GEOMETRY_INVALID")

    for bar in rows_15m:
        if not isinstance(bar, Mapping):
            continue
        close_time = int(bar["close_time"])
        if close_time <= candidate_time:
            continue
        if close_time > candidate_time + max_hold_seconds:
            break
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        if low > high:
            raise ValueError("PAPER_CANDLE_GEOMETRY_INVALID")
        is_long = direction == "LONG"
        stop_hit = low <= stop if is_long else high >= stop
        target_hit = high >= target if is_long else low <= target
        if stop_hit or target_hit:
            ambiguous = bool(stop_hit and target_hit)
            return {
                "outcome": "losses" if stop_hit else "wins",
                "reason": (
                    "STOP_AND_TARGET_SAME_CANDLE_CONSERVATIVE_LOSS"
                    if ambiguous else "STOP_LOSS" if stop_hit else "TAKE_PROFIT"
                ),
                "exit_close_time": close_time,
                "exit_close": close,
                "exit_price": stop if stop_hit else target,
                "ambiguous_same_candle": ambiguous,
                "timeout": False,
            }
        if close_time - candidate_time >= max_hold_seconds:
            return {
                "outcome": "timeouts",
                "reason": "MAX_HOLD_24H" if max_hold_seconds == 86_400 else "MAX_HOLD_REACHED",
                "exit_close_time": close_time,
                "exit_close": close,
                "exit_price": close,
                "ambiguous_same_candle": False,
                "timeout": True,
            }
    return None