"""Fail-closed reader for the Gate.io public closed-candle feeds.

This is an analysis-input boundary, not a signal or execution component.
"""
from __future__ import annotations
import hashlib, json, math, time
from pathlib import Path
from typing import Any

LIVE_WINDOW_CANDLES = 5000

SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"
SPECS = {
    "1m": (60, "data/forward/global_market_candles_1m_v1.jsonl"),
    "15m": (900, "data/forward/global_market_candles_v1.jsonl"),
    "1h": (3600, "data/forward/global_market_candles_1h_v1.jsonl"),
    "4h": (14400, "data/forward/global_market_candles_4h_v1.jsonl"),
}

class MarketDataRejected(ValueError):
    pass

def read_closed_candles(timeframe: str, *, root: str | Path = ".", now: int | None = None,
                        min_bars: int = 200) -> list[dict[str, Any]]:
    if timeframe not in SPECS:
        raise MarketDataRejected("UNSUPPORTED_TIMEFRAME")
    seconds, relative_path = SPECS[timeframe]
    path = Path(root) / relative_path
    if not path.is_file():
        raise MarketDataRejected("CANDLE_FILE_MISSING")
    records=[]
    try:
        # Read only the bounded live window; never truncate the append-only history.
        with path.open("rb") as handle:
            handle.seek(0, 2)
            position = handle.tell()
            chunks = []
            data = b""
            while position > 0 and data.count(bytes([10])) <= LIVE_WINDOW_CANDLES:
                size = min(64 * 1024, position)
                position -= size
                handle.seek(position)
                chunks.insert(0, handle.read(size))
                data = b"".join(chunks)
        lines = data.splitlines()
        if position > 0 and lines:
            lines = lines[1:]
        for line in lines[-LIVE_WINDOW_CANDLES:]:
            if line.strip():
                records.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as exc:
        raise MarketDataRejected("CANDLE_FILE_UNREADABLE") from exc
    if len(records) < min_bars:
        raise MarketDataRejected("INSUFFICIENT_CLOSED_CANDLES")
    previous=None
    for row in records:
        if row.get("schema") != "hes_global_candle_v1":
            raise MarketDataRejected("CANDLE_SCHEMA_INVALID")
        if row.get("source") != SOURCE or row.get("symbol") != SYMBOL or row.get("timeframe") != timeframe:
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
        if quote_volume is None:
            raise MarketDataRejected("CANDLE_QUOTE_VOLUME_INVALID")
        try:
            qv = float(quote_volume)
        except (TypeError, ValueError) as exc:
            raise MarketDataRejected("CANDLE_SCHEMA_INVALID") from exc
        if not math.isfinite(qv) or qv < 0:
            raise MarketDataRejected("CANDLE_QUOTE_VOLUME_INVALID")
        if ts < 0 or ts % seconds:
            raise MarketDataRejected("CANDLE_TIMESTAMP_ALIGNMENT_INVALID")
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

def canonical_market_batch_sha256(rows: list[dict], *, limit: int = 240) -> str:
    """Hash the exact bounded closed-candle rows shared by chart and analysis."""
    if not isinstance(rows, list) or not rows or type(limit) is not int or limit < 1:
        raise ValueError("invalid_canonical_candle_batch")
    canonical_rows = rows[-limit:]
    return hashlib.sha256(
        json.dumps(canonical_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_market_data_batch_provenance(market_input: dict[str, Any], *, limit: int = 240) -> dict[str, Any]:
    """Bind each Strategy V2 timeframe to the same bounded rows exposed by the dashboard."""
    if not isinstance(market_input, dict) or market_input.get("source") != SOURCE or market_input.get("symbol") != SYMBOL:
        raise MarketDataRejected("MARKET_INPUT_IDENTITY_INVALID")
    timeframes = market_input.get("timeframes")
    required = ("15m", "1h", "4h")
    if not isinstance(timeframes, dict) or set(timeframes) != set(required):
        raise MarketDataRejected("MARKET_INPUT_TIMEFRAME_SET_INVALID")
    bound = {}
    for timeframe in required:
        rows = timeframes.get(timeframe)
        if not isinstance(rows, list) or len(rows) < 200:
            raise MarketDataRejected("MARKET_INPUT_BARS_INSUFFICIENT:" + timeframe)
        last_close = rows[-1].get("close_time") if isinstance(rows[-1], dict) else None
        if type(last_close) is not int or last_close <= 0:
            raise MarketDataRejected("MARKET_INPUT_LAST_CLOSE_INVALID:" + timeframe)
        bounded = rows[-limit:]
        bound[timeframe] = {
            "input_batch_sha256": canonical_market_batch_sha256(rows, limit=limit),
            "candle_count": len(bounded),
            "last_closed_candle_time": last_close,
        }
    return {
        "schema": "hes_market_data_batch_provenance_v1",
        "source": SOURCE,
        "symbol": SYMBOL,
        "batch_limit": limit,
        "timeframes": bound,
    }


def load_market_input(*, root: str | Path = ".", now: int | None = None,
                      min_bars: int = 200) -> dict[str, Any]:
    feeds={tf:read_closed_candles(tf,root=root,now=now,min_bars=min_bars) for tf in ("15m","1h","4h")}
    return {
        "schema":"hes_global_market_input_v1",
        "source":SOURCE,
        "symbol":SYMBOL,
        "timeframes":feeds,
        "observed_at":max(row["observed_at"] for rows in feeds.values() for row in rows),
    }
