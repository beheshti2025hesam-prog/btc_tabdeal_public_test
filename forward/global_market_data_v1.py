"""Read-only global market-data provider using Binance public Spot klines.

This adapter is intentionally separate from any venue execution adapter. It uses
only the public market-data endpoint, no credentials, and never submits orders.
Only completed candles are returned; source volume is preserved, not normalized.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://data-api.binance.vision/api/v3/klines"
SUPPORTED_INTERVALS = frozenset({"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"})
INTERVAL_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600,
    "8h": 28800, "12h": 43200, "1d": 86400,
}


class MarketDataError(ValueError):
    """The source response cannot safely be used as canonical market data."""


@dataclass(frozen=True)
class GlobalCandle:
    venue: str
    market: str
    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str = "binance_public_spot_klines"


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise MarketDataError(f"invalid_{field}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise MarketDataError(f"invalid_{field}") from None
    if not number.is_finite():
        raise MarketDataError(f"invalid_{field}")
    return number


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MarketDataError(f"{field}_must_be_timezone_aware")
    return value.astimezone(timezone.utc)


def parse_closed_klines(
    rows: Iterable[object], *, symbol: str, interval: str, as_of: datetime,
    max_latest_age: timedelta | None = None,
) -> tuple[GlobalCandle, ...]:
    """Validate a raw Binance kline array and return closed candles only.

    Historical bars are allowed. If max_latest_age is supplied, only the newest
    returned closed bar is freshness-gated; no gaps are filled or timestamps shifted.
    """
    if not isinstance(symbol, str) or not symbol or symbol != symbol.upper():
        raise MarketDataError("symbol_must_be_explicit_uppercase")
    if interval not in SUPPORTED_INTERVALS:
        raise MarketDataError("unsupported_interval")
    now = _utc(as_of, "as_of")
    duration = timedelta(seconds=INTERVAL_SECONDS[interval])
    parsed: list[GlobalCandle] = []
    seen: set[datetime] = set()
    previous: datetime | None = None

    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) < 7:
            raise MarketDataError(f"malformed_kline_{index}")
        if isinstance(row[0], bool) or isinstance(row[6], bool):
            raise MarketDataError(f"invalid_timestamp_{index}")
        try:
            open_ms, close_ms = int(row[0]), int(row[6])
            start = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc)
            end = datetime.fromtimestamp((close_ms + 1) / 1000, tz=timezone.utc)
        except (ValueError, TypeError, OverflowError, OSError):
            raise MarketDataError(f"invalid_timestamp_{index}") from None
        if start in seen:
            raise MarketDataError("duplicate_candle_open_time")
        if previous is not None and start <= previous:
            raise MarketDataError("candles_not_strictly_chronological")
        if end != start + duration:
            raise MarketDataError("candle_boundary_interval_mismatch")
        seen.add(start)
        previous = start

        values = [_decimal(row[i], name) for i, name in (
            (1, "open"), (2, "high"), (3, "low"), (4, "close"), (5, "volume")
        )]
        op, high, low, close, volume = values
        if min(op, high, low, close) <= 0 or volume < 0:
            raise MarketDataError("invalid_ohlc_or_volume_sign")
        if low > min(op, close) or high < max(op, close) or low > high:
            raise MarketDataError("invalid_ohlc_range")
        # Binance's close timestamp is inclusive; end is normalized to exclusive UTC.
        if end > now:
            continue
        parsed.append(GlobalCandle(
            venue="binance", market="spot", symbol=symbol, interval=interval,
            open_time=start, close_time=end, open=op, high=high, low=low,
            close=close, volume=volume,
        ))

    if not parsed:
        raise MarketDataError("no_fully_closed_candles")
    if max_latest_age is not None:
        if max_latest_age.total_seconds() <= 0:
            raise MarketDataError("max_latest_age_must_be_positive")
        age = now - parsed[-1].close_time
        if age < timedelta(0) or age > max_latest_age:
            raise MarketDataError("latest_closed_candle_stale")
    return tuple(parsed)


def fetch_closed_klines(
    *, symbol: str, interval: str, limit: int = 500,
    as_of: datetime | None = None, max_latest_age: timedelta | None = None,
    timeout_seconds: float = 8.0,
    opener: Callable = urlopen,
) -> tuple[GlobalCandle, ...]:
    """Fetch public Spot klines. Transport errors fail closed; no credentials used."""
    if interval not in SUPPORTED_INTERVALS:
        raise MarketDataError("unsupported_interval")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise MarketDataError("limit_out_of_range")
    if timeout_seconds <= 0:
        raise MarketDataError("timeout_must_be_positive")
    url = BASE_URL + "?" + urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "HES-Trade-Agent-readonly/1"})
    try:
        with opener(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise MarketDataError(f"market_data_http_status_{status}")
            payload = json.loads(response.read().decode("utf-8"))
    except MarketDataError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        raise MarketDataError(f"market_data_transport_or_payload_error:{type(exc).__name__}") from None
    if not isinstance(payload, list):
        raise MarketDataError("unexpected_market_data_payload")
    observed_at = _utc(as_of or datetime.now(timezone.utc), "as_of")
    return parse_closed_klines(
        payload, symbol=symbol, interval=interval, as_of=observed_at,
        max_latest_age=max_latest_age,
    )
