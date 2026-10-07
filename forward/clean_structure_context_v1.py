"""Observation-only multi-candle structure context; no signal generation."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructureContext:
    status: str
    symbol: str
    timeframe: str
    candles: int
    higher_close: bool
    higher_high: bool
    lower_close: bool
    lower_low: bool
    bias: str


class CleanStructureContextV1:
    def observe(self, candles: list[dict[str, Any]]) -> StructureContext:
        if len(candles) < 2:
            raise ValueError("at least two closed candles required")
        for c in candles:
            if c.get("symbol") != "BTC_USDT" or c.get("timeframe") != "15m":
                raise ValueError("unsupported scope")
            if c.get("status") not in {"CANDLE_CLOSED_OBSERVED", "CLOSED"}:
                raise ValueError("closed candles required")
            if float(c["high"]) < float(c["low"]):
                raise ValueError("invalid candle range")
        a, b = candles[-2], candles[-1]
        hc=float(b["close"]) > float(a["close"])
        hh=float(b["high"]) > float(a["high"])
        lc=float(b["close"]) < float(a["close"])
        ll=float(b["low"]) < float(a["low"])
        if hc and hh: bias="UP_CONTEXT"
        elif lc and ll: bias="DOWN_CONTEXT"
        else: bias="MIXED_CONTEXT"
        return StructureContext("STRUCTURE_CONTEXT_OBSERVED","BTC_USDT","15m",len(candles),hh and hc,hh,lc,ll,bias)
