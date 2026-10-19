"""Read-only Binance native OHLCV adapter (Spot and USDⓈ-M Futures).

Network access occurs only when fetch_klines() is explicitly called. Importing
this module performs no I/O. It never places orders or uses credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import re

SPOT_BASE = "https://api.binance.com"
USDM_BASE = "https://fapi.binance.com"
MARKET_BASES = {"spot": SPOT_BASE, "usdm_futures": USDM_BASE}
INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000,
    "4h": 14_400_000, "6h": 21_600_000, "8h": 28_800_000,
    "12h": 43_200_000, "1d": 86_400_000, "3d": 259_200_000,
    "1w": 604_800_000,
}
SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,30}$")


class KlineDataError(ValueError):
    """Raised when an exchange response violates the expected kline schema."""


@dataclass(frozen=True)
class NativeCandle:
    market: str
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
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal

    @property
    def is_closed_by_exchange_time(self) -> bool:
        # A caller still compares close_time_ms against its explicit as_of_ms.
        return True


@dataclass(frozen=True)
class CandleGap:
    expected_open_time_ms: int
    observed_open_time_ms: int


@dataclass(frozen=True)
class KlineBatch:
    market: str
    symbol: str
    interval: str
    retrieved_at_utc: str
    payload_sha256: str
    candles: tuple[NativeCandle, ...]
    gaps: tuple[CandleGap, ...]
    discarded_open_candles: int


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KlineDataError(f"invalid {field}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise KlineDataError(f"invalid {field}") from exc
    if not number.is_finite():
        raise KlineDataError(f"non-finite {field}")
    return number


def parse_klines(
    rows: Any, *, market: str, symbol: str, interval: str,
    as_of_ms: int, retrieved_at: datetime, raw_payload: bytes,
) -> KlineBatch:
    """Validate raw Binance kline arrays; exclude not-yet-closed bars."""
    if market not in MARKET_BASES:
        raise KlineDataError("unsupported market")
    if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol):
        raise KlineDataError("invalid symbol")
    if interval not in INTERVAL_MS:
        raise KlineDataError("unsupported interval")
    if isinstance(as_of_ms, bool) or not isinstance(as_of_ms, int) or as_of_ms < 0:
        raise KlineDataError("invalid as_of_ms")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise KlineDataError("retrieved_at must be timezone-aware")
    if not isinstance(rows, list):
        raise KlineDataError("klines response must be a list")

    step = INTERVAL_MS[interval]
    candles: list[NativeCandle] = []
    gaps: list[CandleGap] = []
    discarded_open = 0
    previous_open: int | None = None
    seen: set[int] = set()

    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) < 12:
            raise KlineDataError(f"invalid kline row at index {index}")
        open_time, close_time, trade_count = row[0], row[6], row[8]
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (open_time, close_time, trade_count)):
            raise KlineDataError(f"invalid integer field at index {index}")
        if open_time < 0 or close_time < open_time or trade_count < 0:
            raise KlineDataError(f"invalid time/count range at index {index}")
        if open_time % step != 0 or close_time != open_time + step - 1:
            raise KlineDataError(f"interval/time alignment mismatch at index {index}")
        if open_time in seen:
            raise KlineDataError(f"duplicate candle open time {open_time}")
        if previous_open is not None:
            if open_time <= previous_open:
                raise KlineDataError("candles must be strictly increasing by open time")
            if open_time > previous_open + step:
                gaps.append(CandleGap(previous_open + step, open_time))
        previous_open = open_time
        seen.add(open_time)

        # Keep open bars out of the closed-candle product; do not mutate them.
        if close_time >= as_of_ms:
            discarded_open += 1
            continue

        o = _decimal(row[1], "open")
        h = _decimal(row[2], "high")
        low = _decimal(row[3], "low")
        c = _decimal(row[4], "close")
        volume = _decimal(row[5], "volume")
        quote_volume = _decimal(row[7], "quote volume")
        taker_base = _decimal(row[9], "taker-buy base volume")
        taker_quote = _decimal(row[10], "taker-buy quote volume")
        if min(o, h, low, c) <= 0 or min(volume, quote_volume, taker_base, taker_quote) < 0:
            raise KlineDataError(f"negative/zero price or negative volume at index {index}")
        if h < max(o, c, low) or low > min(o, c, h):
            raise KlineDataError(f"inconsistent OHLC range at index {index}")

        candles.append(NativeCandle(
            market=market, symbol=symbol, interval=interval,
            open_time_ms=open_time, close_time_ms=close_time,
            open=o, high=h, low=low, close=c, volume=volume,
            quote_volume=quote_volume, trade_count=trade_count,
            taker_buy_base_volume=taker_base,
            taker_buy_quote_volume=taker_quote,
        ))

    return KlineBatch(
        market=market, symbol=symbol, interval=interval,
        retrieved_at_utc=retrieved_at.astimezone(timezone.utc).isoformat(),
        payload_sha256=sha256(raw_payload).hexdigest(),
        candles=tuple(candles), gaps=tuple(gaps),
        discarded_open_candles=discarded_open,
    )


def fetch_klines(
    *, market: str, symbol: str = "BTCUSDT", interval: str = "15m",
    limit: int = 500, timeout_seconds: float = 8.0,
    as_of: datetime | None = None,
) -> KlineBatch:
    """Fetch public native OHLCV from Binance; never called implicitly."""
    if market not in MARKET_BASES:
        raise KlineDataError("unsupported market")
    if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol):
        raise KlineDataError("invalid symbol")
    if interval not in INTERVAL_MS:
        raise KlineDataError("unsupported interval")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1500:
        raise KlineDataError("limit must be an integer from 1 to 1500")
    if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 10:
        raise KlineDataError("timeout must be greater than 0 and at most 10 seconds")
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise KlineDataError("as_of must be timezone-aware")

    path = "/api/v3/klines" if market == "spot" else "/fapi/v1/klines"
    url = MARKET_BASES[market] + path + "?" + urlencode({
        "symbol": symbol, "interval": interval, "limit": limit,
    })
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "HES-Trade-Agent-readonly/1"})
    try:
        with urlopen(request, timeout=float(timeout_seconds)) as response:
            raw = response.read()
    except Exception as exc:
        raise RuntimeError(f"native kline request failed: {type(exc).__name__}") from exc
    try:
        rows = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KlineDataError("invalid JSON response") from exc
    return parse_klines(
        rows, market=market, symbol=symbol, interval=interval,
        as_of_ms=int(as_of.timestamp() * 1000), retrieved_at=datetime.now(timezone.utc),
        raw_payload=raw,
    )
