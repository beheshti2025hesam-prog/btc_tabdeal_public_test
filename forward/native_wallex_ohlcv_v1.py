"""Read-only native Wallex OHLCV adapter (Candle-First, no trade-sequence dependency).

Official endpoint documented by Wallex:
GET https://api.wallex.ir/v1/udf/history
Query: symbol, resolution (minutes), from/to (Unix seconds).
Response arrays: s, t, o, h, l, c, v.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json


WALLEX_HISTORY_URL = "https://api.wallex.ir/v1/udf/history"


@dataclass(frozen=True)
class NativeCandle:
    symbol: str
    timeframe_minutes: int
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool
    source: str = "wallex_native_udf_history"


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"invalid {field}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid {field}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite {field}")
    return result


def parse_history(
    payload: Mapping[str, Any],
    *,
    symbol: str,
    timeframe_minutes: int,
    as_of: datetime,
) -> tuple[NativeCandle, ...]:
    """Parse native endpoint data without fabricating gaps or reordering rows."""
    if not symbol or timeframe_minutes <= 0:
        raise ValueError("symbol and positive timeframe_minutes are required")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if payload.get("s") != "ok":
        raise ValueError(f"Wallex history status is not ok: {payload.get('s')!r}")

    columns = {name: payload.get(name) for name in ("t", "o", "h", "l", "c", "v")}
    if any(not isinstance(value, list) for value in columns.values()):
        raise ValueError("OHLCV columns must be arrays")
    lengths = {len(value) for value in columns.values()}
    if len(lengths) != 1:
        raise ValueError("OHLCV column length mismatch")

    as_of_utc = as_of.astimezone(timezone.utc)
    duration_seconds = timeframe_minutes * 60
    result: list[NativeCandle] = []
    previous_open: int | None = None

    for i, raw_ts in enumerate(columns["t"]):
        if isinstance(raw_ts, bool):
            raise ValueError("invalid candle timestamp")
        try:
            timestamp = int(raw_ts)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid candle timestamp") from exc
        if timestamp <= 0 or timestamp != raw_ts:
            raise ValueError("invalid candle timestamp")
        if timestamp % duration_seconds != 0:
            raise ValueError("candle timestamp is not timeframe-aligned")
        if previous_open is not None and timestamp <= previous_open:
            raise ValueError("candle timestamps must be strictly increasing")
        previous_open = timestamp

        o = _decimal(columns["o"][i], "open")
        h = _decimal(columns["h"][i], "high")
        low = _decimal(columns["l"][i], "low")
        c = _decimal(columns["c"][i], "close")
        v = _decimal(columns["v"][i], "volume")
        if min(o, h, low, c) <= 0 or v < 0:
            raise ValueError("prices must be positive and volume non-negative")
        if h < max(o, c, low) or low > min(o, c, h):
            raise ValueError("inconsistent OHLC bounds")

        open_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        close_time = datetime.fromtimestamp(timestamp + duration_seconds, tz=timezone.utc)
        result.append(NativeCandle(
            symbol=symbol,
            timeframe_minutes=timeframe_minutes,
            open_time=open_time,
            close_time=close_time,
            open=o, high=h, low=low, close=c, volume=v,
            is_closed=close_time <= as_of_utc,
        ))
    return tuple(result)


def fetch_native_ohlcv(
    *,
    symbol: str,
    timeframe_minutes: int,
    start: datetime,
    end: datetime,
    as_of: datetime,
    timeout_seconds: float = 10.0,
    transport: Callable[[str, float], bytes] | None = None,
) -> tuple[NativeCandle, ...]:
    """Fetch public native candles. Read-only; injectable transport supports tests."""
    if not symbol or any(ch.isspace() for ch in symbol):
        raise ValueError("invalid symbol")
    if timeframe_minutes <= 0 or timeout_seconds <= 0:
        raise ValueError("timeframe and timeout must be positive")
    for label, value in (("start", start), ("end", end), ("as_of", as_of)):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{label} must be timezone-aware")
    start_ts = int(start.astimezone(timezone.utc).timestamp())
    end_ts = int(end.astimezone(timezone.utc).timestamp())
    if start_ts < 0 or end_ts <= start_ts:
        raise ValueError("invalid requested time range")
    query = urlencode({
        "symbol": symbol,
        "resolution": str(timeframe_minutes),
        "from": str(start_ts),
        "to": str(end_ts),
    })
    url = f"{WALLEX_HISTORY_URL}?{query}"

    def default_transport(request_url: str, timeout: float) -> bytes:
        request = Request(request_url, headers={"Accept": "application/json", "User-Agent": "HES-Trade-Agent-readonly/1"})
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"Wallex history HTTP status {response.status}")
            return response.read()

    raw = (transport or default_transport)(url, timeout_seconds)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Wallex response must be a JSON object")
    return parse_history(payload, symbol=symbol, timeframe_minutes=timeframe_minutes, as_of=as_of)
