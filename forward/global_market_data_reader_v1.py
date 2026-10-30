"""Fail-closed reader for the Gate.io public closed-candle feeds.

This is an analysis-input boundary, not a signal or execution component.
"""
from __future__ import annotations
import json, math, time
from pathlib import Path
from typing import Any

SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"
SPECS = {
    "15m": (900, "data/forward/global_market_candles_v1.jsonl"),
    "1h": (3600, "data/forward/global_market_candles_1h_v1.jsonl"),
    "4h": (14400, "data/forward/global_market_candles_4h_v1.jsonl"),
}

SYMBOL_PATHS = {
    "BTC_USDT": SPECS,
    "ETH_USDT": {
        "15m": (900, "data/forward/global_market_candles_ETH_USDT_15m_v1.jsonl"),
        "1h": (3600, "data/forward/global_market_candles_ETH_USDT_1h_v1.jsonl"),
        "4h": (14400, "data/forward/global_market_candles_ETH_USDT_4h_v1.jsonl"),
    },
    "SOL_USDT": {
        "15m": (900, "data/forward/global_market_candles_SOL_USDT_15m_v1.jsonl"),
        "1h": (3600, "data/forward/global_market_candles_SOL_USDT_1h_v1.jsonl"),
        "4h": (14400, "data/forward/global_market_candles_SOL_USDT_4h_v1.jsonl"),
    },
}

class MarketDataRejected(ValueError):
    pass

def read_closed_candles(timeframe: str, *, root: str | Path = ".", now: int | None = None,
                        min_bars: int = 200, symbol: str = SYMBOL) -> list[dict[str, Any]]:
    if symbol not in SYMBOL_PATHS:
        raise MarketDataRejected("UNSUPPORTED_SYMBOL")
    specs = SYMBOL_PATHS[symbol]
    if timeframe not in specs:
        raise MarketDataRejected("UNSUPPORTED_TIMEFRAME")
    seconds, relative_path = specs[timeframe]
    path = Path(root) / relative_path
    if not path.is_file():
        raise MarketDataRejected("CANDLE_FILE_MISSING")
    records=[]
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as exc:
        raise MarketDataRejected("CANDLE_FILE_UNREADABLE") from exc
    if len(records) < min_bars:
        raise MarketDataRejected("INSUFFICIENT_CLOSED_CANDLES")
    previous=None
    for row in records:
        if row.get("source") != SOURCE or row.get("symbol") != symbol or row.get("timeframe") != timeframe:
            raise MarketDataRejected("SOURCE_IDENTITY_MISMATCH")
        if row.get("closed") is not True:
            raise MarketDataRejected("OPEN_CANDLE_REJECTED")
        try:
            ts=int(row["open_time"]); close_time=int(row["close_time"])
            o=float(row["open"]); h=float(row["high"]); l=float(row["low"]); c=float(row["close"]); v=float(row["volume"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketDataRejected("CANDLE_SCHEMA_INVALID") from exc
        if not all(math.isfinite(value) for value in (o,h,l,c,v)):
            raise MarketDataRejected("CANDLE_NON_FINITE_VALUE")
        quote_volume = row.get("quote_volume")
        if quote_volume is not None:
            try:
                qv = float(quote_volume)
            except (TypeError, ValueError) as exc:
                raise MarketDataRejected("CANDLE_SCHEMA_INVALID") from exc
            if not math.isfinite(qv) or qv < 0:
                raise MarketDataRejected("CANDLE_QUOTE_VOLUME_INVALID")
        if close_time != ts + seconds or min(o,h,l,c) <= 0 or v < 0 or h < max(o,c,l) or l > min(o,c,h):
            raise MarketDataRejected("CANDLE_OHLC_INVALID")
        if previous is not None:
            if ts <= previous:
                raise MarketDataRejected("CANDLE_ORDER_OR_DUPLICATE")
            if ts - previous != seconds:
                raise MarketDataRejected("CANDLE_INTERVAL_GAP")
        previous=ts
    now_s=int(time.time()) if now is None else int(now)
    age=now_s-int(records[-1]["close_time"])
    if age < 0:
        raise MarketDataRejected("CANDLE_CLOSE_IN_FUTURE")
    if age > seconds * 2:
        raise MarketDataRejected("CANDLE_FEED_STALE")
    return records

def load_market_input(*, root: str | Path = ".", now: int | None = None,
                      min_bars: int = 200, symbol: str = SYMBOL) -> dict[str, Any]:
    if symbol not in SYMBOL_PATHS:
        raise MarketDataRejected("UNSUPPORTED_SYMBOL")
    feeds={tf:read_closed_candles(tf,root=root,now=now,min_bars=min_bars,symbol=symbol) for tf in ("15m","1h","4h")}
    return {
        "schema":"hes_global_market_input_v1",
        "source":SOURCE,
        "symbol":symbol,
        "timeframes":feeds,
        "observed_at":max(row["observed_at"] for rows in feeds.values() for row in rows),
    }
