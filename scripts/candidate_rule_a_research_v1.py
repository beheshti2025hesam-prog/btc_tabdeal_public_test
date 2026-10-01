"""Deterministic Rule A research construction.

Research-only. No optimization, fitting, execution, or promotion.
"""

from __future__ import annotations

import math
from typing import Any


def evaluate_rule_a(buy_ratio: float, buy_sell_delta: float, trade_count: float) -> str:
    """Return LONG, SHORT, or NO_TRADE from frozen Rule A inputs."""
    values = (buy_ratio, buy_sell_delta, trade_count)
    if not all(math.isfinite(float(v)) for v in values):
        return "NO_TRADE"

    if buy_ratio > 0.5 and buy_sell_delta > 0:
        return "LONG"
    if buy_ratio < 0.5 and buy_sell_delta < 0:
        return "SHORT"
    return "NO_TRADE"


def evaluate_row(row: dict[str, Any]) -> str:
    return evaluate_rule_a(
        float(row["buy_ratio"]),
        float(row["buy_sell_delta"]),
        float(row["trade_count"]),
    )
