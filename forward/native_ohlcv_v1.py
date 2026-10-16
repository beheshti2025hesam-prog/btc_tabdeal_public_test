"""Read-only native OHLCV adapters for exchange-provided candles.

The primary market-data path is venue candle data, not candles reconstructed
from trades. Network access is explicit, public-only, and limited to the
hard-coded Binance public endpoints below. No keys, orders, or account APIs.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Fixed-duration intervals only. Calendar-month and week intervals are omitted
# until their venue-specific UTC alignment rules are explicitly implemented.
INTERVAL_MS: dict[str, int] = {
    "1s": 1_000, "1m": 60_000, "3m": 180_000, "5m": 300_000,
    "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000,
    "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000,
    "3d": 259_200_000,
}
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{5,20}$")
_HTTP_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class NativeCandle:
    venue: str
    product: str
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
    closed: bool = True


@dataclass(frozen=True)
class CandleGap:
    expected_open_time_ms: int
    next_observed_open_time_ms: int
    missing_intervals: int


@dataclass(frozen=True)
class NativeOHLCVBatch:
    venue: str
    product: str
    symbol: str
    interval: str
    endpoint_kind: str
    fetched_at_ms: int
    response_sha256: str
    candles: tuple[NativeCandle, ...]
    gaps: tuple[CandleGap, ...]
    open_candles_excluded: int


def _wire_int(value: object, field: str) -> int:
    if type(value) is int:
        return value
    if type(value) is str and value and value.isdecimal():
        return int(value)
    raise ValueError(f"{field} must be an integer wire value")


def _decimal(value: object, field: str) -> Decimal:
    if type(value) not in (str, int, float, Decimal):
        raise ValueError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} is not a decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _canonical_row(row: object, interval_ms: int) -> tuple:
    if not isinstance(row, (list, tuple)) or len(row) != 12:
        raise ValueError("kline row must contain exactly 12 fields")
    open_time = _wire_int(row[0], "open_time")
    close_time = _wire_int(row[6], "close_time")
    open_price = _decimal(row[1], "open")
    high = _decimal(row[2], "high")
    low = _decimal(row[3], "low")
    close = _decimal(row[4], "close")
    volume = _decimal(row[5], "volume")
    quote_volume = _decimal(row[7], "quote_volume")
    trade_count = _wire_int(row[8], "trade_count")
    if open_time < 0 or close_time < open_time:
        raise ValueError("invalid candle timestamps")
    if open_time % interval_ms != 0:
        raise ValueError("candle open_time is not aligned to the requested interval")
    if close_time != open_time + interval_ms - 1:
        raise ValueError("candle close_time does not match the fixed interval")
    if min(open_price, high, low, close) <= 0:
        raise ValueError("OHLC prices must be positive")
    if high < max(open_price, low, close) or low > min(open_price, high, close):
        raise ValueError("OHLC relationship is invalid")
    if volume < 0 or quote_volume < 0 or trade_count < 0:
        raise ValueError("volume and trade_count must be non-negative")
    if _decimal(row[9], "taker_buy_base_volume") < 0:
        raise ValueError("taker-buy base volume must be non-negative")
    if _decimal(row[10], "taker_buy_quote_volume") < 0:
        raise ValueError("taker-buy quote volume must be non-negative")
    if type(row[11]) not in (str, int) or str(row[11]) not in ("0", "0.0"):
        raise ValueError("reserved kline field must be zero")
    return (open_time, close_time, open_price, high, low, close, volume, quote_volume, trade_count)


def normalize_native_klines(
    rows: Iterable[object], *, venue: str, product: str, symbol: str,
    interval: str, endpoint_kind: str, as_of_ms: int, fetched_at_ms: int,
    response_sha256: str,
) -> NativeOHLCVBatch:
    """Validate native candles, exclude unfinished bars, and expose gaps.

    Gaps are reported only between returned closed candles; absent data before
    the first or after the last returned candle is not inferred.
    """
    if venue != "binance":
        raise ValueError("unsupported venue")
    if product not in {"spot", "usdm_perpetual"}:
        raise ValueError("unsupported product")
    if not isinstance(symbol, str) or not _SYMBOL_RE.fullmatch(symbol):
        raise ValueError("invalid symbol")
    if interval not in INTERVAL_MS:
        raise ValueError("unsupported fixed interval")
    for name, value in (("as_of_ms", as_of_ms), ("fetched_at_ms", fetched_at_ms)):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if not re.fullmatch(r"[0-9a-f]{64}", response_sha256):
        raise ValueError("response_sha256 must be lowercase SHA-256 hex")

    interval_ms = INTERVAL_MS[interval]
    canonical: dict[int, tuple] = {}
    previous_open: int | None = None
    open_candles_excluded = 0
    for row in rows:
        item = _canonical_row(row, interval_ms)
        open_time, close_time = item[0], item[1]
        if previous_open is not None and open_time < previous_open:
            raise ValueError("source candles are not ordered by open_time")
        previous_open = open_time
        if open_time > as_of_ms:
            raise ValueError("source returned a candle from the future")
        existing = canonical.get(open_time)
        if existing is not None:
            if existing != item:
                raise ValueError("conflicting duplicate candle open_time")
            continue
        canonical[open_time] = item
        if close_time >= as_of_ms:
            open_candles_excluded += 1

    candles: list[NativeCandle] = []
    for open_time, item in canonical.items():
        close_time = item[1]
        if close_time >= as_of_ms:
            continue
        candles.append(NativeCandle(
            venue=venue, product=product, symbol=symbol, interval=interval,
            open_time_ms=open_time, close_time_ms=close_time,
            open=item[2], high=item[3], low=item[4], close=item[5],
            volume=item[6], quote_volume=item[7], trade_count=item[8],
        ))

    gaps: list[CandleGap] = []
    for previous, current in zip(candles, candles[1:]):
        distance = current.open_time_ms - previous.open_time_ms
        if distance > interval_ms:
            gaps.append(CandleGap(
                expected_open_time_ms=previous.open_time_ms + interval_ms,
                next_observed_open_time_ms=current.open_time_ms,
                missing_intervals=(distance // interval_ms) - 1,
            ))
        elif distance < interval_ms:
            raise ValueError("overlapping native candle intervals")

    return NativeOHLCVBatch(
        venue=venue, product=product, symbol=symbol, interval=interval,
        endpoint_kind=endpoint_kind, fetched_at_ms=fetched_at_ms,
        response_sha256=response_sha256, candles=tuple(candles),
        gaps=tuple(gaps), open_candles_excluded=open_candles_excluded,
    )


def _http_get(url: str, timeout_seconds: int = _HTTP_TIMEOUT_SECONDS) -> bytes:
    request = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "HES-Native-OHLCV/1.0",
    }, method="GET")
    with urlopen(request, timeout=timeout_seconds) as response:
        if response.status != 200:
            raise RuntimeError(f"public kline endpoint returned HTTP {response.status}")
        return response.read()


class BinanceNativeKlineSource:
    """Read-only public Binance candle source; no credentials or write methods."""

    venue = "binance"

    def __init__(
        self, *, product: str, chart_optimized: bool = False,
        transport: Callable[[str, int], bytes] | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if product == "spot":
            self.endpoint = (
                "https://api.binance.com/api/v3/uiKlines"
                if chart_optimized else "https://api.binance.com/api/v3/klines"
            )
            self.max_limit = 1000
        elif product == "usdm_perpetual":
            if chart_optimized:
                raise ValueError("chart_optimized mode is not documented for USDⓈ-M Futures")
            self.endpoint = "https://fapi.binance.com/fapi/v1/klines"
            self.max_limit = 1500
        else:
            raise ValueError("unsupported product")
        self.product = product
        self.endpoint_kind = "uiKlines" if "/uiKlines" in self.endpoint else "klines"
        self._transport = transport or _http_get
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    def fetch(
        self, *, symbol: str, interval: str = "15m", limit: int = 100,
        start_time_ms: int | None = None, end_time_ms: int | None = None,
        as_of_ms: int | None = None,
    ) -> NativeOHLCVBatch:
        if interval not in INTERVAL_MS:
            raise ValueError("unsupported fixed interval")
        if type(limit) is not int or not 1 <= limit <= self.max_limit:
            raise ValueError(f"limit must be between 1 and {self.max_limit}")
        if not isinstance(symbol, str) or not _SYMBOL_RE.fullmatch(symbol):
            raise ValueError("invalid symbol")
        if start_time_ms is not None and (type(start_time_ms) is not int or start_time_ms < 0):
            raise ValueError("start_time_ms must be a non-negative integer")
        if end_time_ms is not None and (type(end_time_ms) is not int or end_time_ms < 0):
            raise ValueError("end_time_ms must be a non-negative integer")
        if start_time_ms is not None and end_time_ms is not None and start_time_ms > end_time_ms:
            raise ValueError("start_time_ms must not exceed end_time_ms")

        params: dict[str, object] = {"symbol": symbol, "interval": interval, "limit": limit}
        if self.product == "spot":
            params["timeZone"] = "0"
        if start_time_ms is not None:
            params["startTime"] = start_time_ms
        if end_time_ms is not None:
            params["endTime"] = end_time_ms
        url = self.endpoint + "?" + urlencode(params)
        body = self._transport(url, _HTTP_TIMEOUT_SECONDS)
        if not isinstance(body, bytes):
            raise ValueError("transport must return raw response bytes")
        digest = hashlib.sha256(body).hexdigest()
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON from public kline endpoint") from exc
        if not isinstance(payload, list):
            raise ValueError("public kline response must be a list")
        fetched_at_ms = self._clock_ms()
        effective_as_of_ms = fetched_at_ms if as_of_ms is None else as_of_ms
        return normalize_native_klines(
            payload, venue=self.venue, product=self.product, symbol=symbol,
            interval=interval, endpoint_kind=self.endpoint_kind,
            as_of_ms=effective_as_of_ms, fetched_at_ms=fetched_at_ms,
            response_sha256=digest,
        )


class BinanceSpotKlineSource(BinanceNativeKlineSource):
    def __init__(self, *, chart_optimized: bool = False, **kwargs: object) -> None:
        super().__init__(product="spot", chart_optimized=chart_optimized, **kwargs)


class BinanceUsdMPerpetualKlineSource(BinanceNativeKlineSource):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(product="usdm_perpetual", **kwargs)
