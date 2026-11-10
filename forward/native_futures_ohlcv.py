"""Read-only native Binance USDⓈ-M Futures kline adapter.

No credentials, order endpoints, websocket subscriptions, or trading side effects.
Raw response bytes and their SHA-256 are returned together for evidence capture.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://fapi.binance.com/fapi/v1/klines"
INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000,
    "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000,
    "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000,
    "3d": 259_200_000, "1w": 604_800_000,
}


@dataclass(frozen=True)
class NativeCandle:
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int
    taker_buy_volume: Decimal
    taker_buy_quote_volume: Decimal
    is_closed: bool


@dataclass(frozen=True)
class KlineEvidence:
    requested_url: str
    retrieved_at_utc: str
    http_status: int
    raw_body: bytes
    raw_sha256: str
    candles: tuple[NativeCandle, ...]


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid decimal field: {field}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite decimal field: {field}")
    return result


def parse_klines(raw_body: bytes, *, symbol: str, interval: str,
                 now_ms: int) -> tuple[NativeCandle, ...]:
    """Parse the official 12-column kline arrays without float conversion."""
    if interval not in INTERVAL_MS:
        raise ValueError(f"unsupported interval: {interval}")
    try:
        rows = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("response is not valid JSON") from exc
    if not isinstance(rows, list):
        raise ValueError("kline response must be a list")
    result: list[NativeCandle] = []
    seen: set[int] = set()
    duration = INTERVAL_MS[interval]
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != 12:
            raise ValueError(f"kline row {index} must contain 12 fields")
        try:
            open_ms, close_ms = int(row[0]), int(row[6])
            count = int(row[8])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid integer in kline row {index}") from exc
        if open_ms in seen:
            raise ValueError(f"duplicate kline open time: {open_ms}")
        seen.add(open_ms)
        if open_ms % duration != 0 or close_ms != open_ms + duration - 1:
            raise ValueError(f"misaligned kline interval at {open_ms}")
        o, h, low, c = (_decimal(row[i], ("open", "high", "low", "close")[j])
                        for j, i in enumerate((1, 2, 3, 4)))
        volume, quote = _decimal(row[5], "volume"), _decimal(row[7], "quote_volume")
        taker_volume = _decimal(row[9], "taker_buy_volume")
        taker_quote = _decimal(row[10], "taker_buy_quote_volume")
        if min(o, h, low, c, volume, quote, taker_volume, taker_quote) < 0:
            raise ValueError(f"negative market value in kline row {index}")
        if h < max(o, c, low) or low > min(o, c, h):
            raise ValueError(f"inconsistent OHLC range in kline row {index}")
        if count < 0 or taker_volume > volume:
            raise ValueError(f"inconsistent volume/trade count in kline row {index}")
        result.append(NativeCandle(
            symbol=symbol, interval=interval, open_time_ms=open_ms,
            close_time_ms=close_ms, open=o, high=h, low=low, close=c,
            volume=volume, quote_volume=quote, trade_count=count,
            taker_buy_volume=taker_volume,
            taker_buy_quote_volume=taker_quote,
            is_closed=close_ms < now_ms,
        ))
    return tuple(sorted(result, key=lambda candle: candle.open_time_ms))


def fetch_futures_klines(symbol: str = "BTCUSDT", interval: str = "15m",
                         limit: int = 100, timeout_seconds: float = 10.0) -> KlineEvidence:
    """Fetch public USDⓈ-M Futures candles; preserve exact response bytes and hash."""
    if not symbol or not symbol.isascii() or not symbol.isalnum():
        raise ValueError("symbol must be an ASCII alphanumeric exchange symbol")
    if interval not in INTERVAL_MS:
        raise ValueError(f"unsupported interval: {interval}")
    if not 1 <= limit <= 1500:
        raise ValueError("limit must be between 1 and 1500")
    from urllib.parse import urlencode
    query = urlencode({"symbol": symbol.upper(), "interval": interval, "limit": limit})
    url = f"{BASE_URL}?{query}"
    request = Request(url, headers={"Accept": "application/json",
                                    "User-Agent": "HES-Trade-Agent-readonly/1.0"})
    retrieved_at = datetime.now(timezone.utc).isoformat()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = response.status
            raw = response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"public kline request failed: {type(exc).__name__}") from exc
    if status != 200:
        raise RuntimeError(f"public kline endpoint returned HTTP {status}")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    candles = parse_klines(raw, symbol=symbol.upper(), interval=interval, now_ms=now_ms)
    return KlineEvidence(url, retrieved_at, status, raw, sha256(raw).hexdigest(), candles)
