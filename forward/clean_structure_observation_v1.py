"""Observation-only market structure extraction from closed forward candles."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructureObservation:
    status: str
    symbol: str
    timeframe: str
    observed_at: Any
    high: float
    low: float
    close: float
    direction: str


class CleanStructureObservationV1:
    def observe(self, candle: dict[str, Any], *, observed_at) -> StructureObservation:
        if not candle:
            raise ValueError("missing candle")
        if candle.get("symbol") != "BTC_USDT":
            raise ValueError("unsupported symbol")
        if candle.get("timeframe") != "15m":
            raise ValueError("unsupported timeframe")
        if candle.get("status") not in {"CANDLE_CLOSED_OBSERVED", "CLOSED"}:
            raise ValueError("closed candle required")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        values = {k: float(candle[k]) for k in ("high", "low", "close")}
        if values["high"] < values["low"]:
            raise ValueError("invalid candle range")
        direction = "UP" if values["close"] > float(candle.get("open", values["close"])) else "DOWN" if values["close"] < float(candle.get("open", values["close"])) else "FLAT"
        return StructureObservation("STRUCTURE_OBSERVED", "BTC_USDT", "15m", observed_at, values["high"], values["low"], values["close"], direction)
