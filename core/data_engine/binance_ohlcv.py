"""Read-only native Binance OHLCV adapter (v1).

This module only reads public candle endpoints. It does not access credentials,
accounts, order endpoints, or WebSocket streams. Prices and volume remain source
decimal strings so downstream code can choose its own Decimal conversion policy.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_BASE_URLS = {
    "spot": "https://api.binance.com",
    "usdm": "https://fapi.binance.com",
}
_ALLOWED_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h",
    "12h", "1d", "3d", "1w", "1M",
}


class BinanceOHLCVError(RuntimeError):
    """Raised when Binance returns an invalid response or a read fails."""


@dataclass(frozen=True)
class NativeCandle:
    venue: str
    market_type: str
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    quote_volume: str
    trade_count: int
    is_closed: bool

    def as_dict(self) -> dict[str, Any]:
        result = dict(self.__dict__)
        result["open_time_utc"] = datetime.fromtimestamp(
            self.open_time_ms / 1000, tz=timezone.utc
        ).isoformat()
        result["close_time_utc"] = datetime.fromtimestamp(
            self.close_time_ms / 1000, tz=timezone.utc
        ).isoformat()
        return result


def _http_get_json(url: str, timeout: float) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "HES-Trade-Agent-readonly-ohlcv/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise BinanceOHLCVError(f"Unexpected HTTP status: {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BinanceOHLCVError(f"Binance public kline read failed: {exc}") from exc


def fetch_closed_candles(
    symbol: str = "BTCUSDT",
    interval: str = "15m",
    limit: int = 100,
    market_type: str = "spot",
    *,
    now_ms: int | None = None,
    timeout: float = 8.0,
    transport: Callable[[str, float], Any] = _http_get_json,
) -> list[NativeCandle]:
    """Fetch closed native OHLCV candles from Binance Spot or USDⓈ-M Futures.

    The currently forming candle is deliberately excluded. No gaps are filled.
    Timestamps and decimal fields are kept in the source's original units/strings.
    A transport can be injected for deterministic tests; production defaults to
    a bounded-timeout HTTPS GET against a fixed official public endpoint.
    """
    if market_type not in _BASE_URLS:
        raise ValueError("market_type must be 'spot' or 'usdm'")
    if not isinstance(symbol, str) or not symbol or not symbol.isascii():
        raise ValueError("symbol must be a non-empty ASCII string")
    if not symbol.isalnum() or symbol.upper() != symbol:
        raise ValueError("symbol must contain uppercase ASCII letters/digits only")
    if interval not in _ALLOWED_INTERVALS:
        raise ValueError("unsupported Binance kline interval")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer from 1 to 1000")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    path = "/api/v3/klines" if market_type == "spot" else "/fapi/v1/klines"
    url = _BASE_URLS[market_type] + path + "?" + urlencode(
        {"symbol": symbol, "interval": interval, "limit": limit}
    )
    payload = transport(url, timeout)
    if not isinstance(payload, list):
        raise BinanceOHLCVError("Kline response must be a JSON array")

    current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    parsed: list[NativeCandle] = []
    previous_open = -1
    for row in payload:
        if not isinstance(row, list) or len(row) < 11:
            raise BinanceOHLCVError("Kline row has an invalid shape")
        try:
            open_ms, close_ms = int(row[0]), int(row[6])
            values = [str(row[index]) for index in (1, 2, 3, 4, 5, 7)]
            trade_count = int(row[8])
        except (TypeError, ValueError, IndexError) as exc:
            raise BinanceOHLCVError("Kline row contains invalid numeric fields") from exc
        if open_ms < 0 or close_ms < open_ms or open_ms <= previous_open:
            raise BinanceOHLCVError("Kline timestamps are invalid or not strictly ordered")
        if trade_count < 0:
            raise BinanceOHLCVError("Kline trade count cannot be negative")
        previous_open = open_ms
        if close_ms >= current_ms:
            continue
        parsed.append(
            NativeCandle(
                venue="binance",
                market_type=market_type,
                symbol=symbol,
                interval=interval,
                open_time_ms=open_ms,
                close_time_ms=close_ms,
                open=values[0],
                high=values[1],
                low=values[2],
                close=values[3],
                volume=values[4],
                quote_volume=values[5],
                trade_count=trade_count,
                is_closed=True,
            )
        )
    return parsed
