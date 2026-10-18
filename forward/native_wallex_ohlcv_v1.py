"""Read-only native Wallex OHLCV adapter; candle path has no trade-sequence dependency.

Official endpoint: GET https://api.wallex.ir/v1/udf/history
Documented minute resolutions supported here: 1, 60, 180, 360, 720.
Wallex also documents 1D, but daily-boundary/chart parity is deliberately deferred.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import math
import time


WALLEX_HISTORY_URL = "https://api.wallex.ir/v1/udf/history"
SUPPORTED_MINUTE_RESOLUTIONS = frozenset({1, 60, 180, 360, 720})


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


@dataclass(frozen=True)
class NativeFetchEvidence:
    request_url: str
    retrieved_at: datetime
    raw_response: bytes
    raw_sha256: str
    server_date_header: str | None
    server_clock_offset_seconds: float | None
    attempt_count: int
    candles: tuple[NativeCandle, ...]


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


def _validate_resolution(timeframe_minutes: int) -> None:
    if isinstance(timeframe_minutes, bool) or not isinstance(timeframe_minutes, int):
        raise ValueError("timeframe_minutes must be an integer")
    if timeframe_minutes not in SUPPORTED_MINUTE_RESOLUTIONS:
        raise ValueError("unsupported resolution; use a documented minute resolution: 1, 60, 180, 360, 720")


def parse_history(
    payload: Mapping[str, Any],
    *,
    symbol: str,
    timeframe_minutes: int,
    as_of: datetime,
) -> tuple[NativeCandle, ...]:
    """Parse native endpoint data without fabricating gaps or reordering rows."""
    if not isinstance(payload, Mapping):
        raise ValueError("Wallex response must be a JSON object")
    if not isinstance(symbol, str) or not symbol or any(ch.isspace() for ch in symbol):
        raise ValueError("symbol is required and must not contain whitespace")
    _validate_resolution(timeframe_minutes)
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
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
        # UDF history defines t as Unix timestamps. Accept only integral JSON values;
        # don't silently coerce booleans, floats, or strings into timestamps.
        if isinstance(raw_ts, bool) or not isinstance(raw_ts, int) or raw_ts <= 0:
            raise ValueError("candle timestamp must be a positive integer Unix timestamp")
        timestamp = raw_ts
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


def fetch_native_ohlcv_evidence(
    *,
    symbol: str,
    timeframe_minutes: int,
    start: datetime,
    end: datetime,
    as_of: datetime,
    timeout_seconds: float = 10.0,
    transport: Callable[[str, float], bytes] | None = None,
    clock: Callable[[], datetime] | None = None,
    max_attempts: int = 3,
    retry_backoff_seconds: float = 0.25,
    sleep: Callable[[float], None] | None = None,
) -> NativeFetchEvidence:
    """Fetch read-only history and retain exact response bytes plus SHA-256 evidence."""
    if not isinstance(symbol, str) or not symbol or any(ch.isspace() for ch in symbol):
        raise ValueError("invalid symbol")
    _validate_resolution(timeframe_minutes)
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(float(timeout_seconds)) or timeout_seconds <= 0:
        raise ValueError("timeout must be a finite positive number")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 5:
        raise ValueError("max_attempts must be an integer from 1 to 5")
    if isinstance(retry_backoff_seconds, bool) or not isinstance(retry_backoff_seconds, (int, float)) or not math.isfinite(float(retry_backoff_seconds)) or not 0 <= retry_backoff_seconds <= 10:
        raise ValueError("retry_backoff_seconds must be finite and between 0 and 10 seconds")
    for label, value in (("start", start), ("end", end), ("as_of", as_of)):
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
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

    response_headers: dict[str, str] = {}

    def default_transport(request_url: str, timeout: float) -> bytes:
        request = Request(
            request_url,
            headers={"Accept": "application/json", "User-Agent": "HES-Trade-Agent-readonly/1"},
        )
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"Wallex history HTTP status {response.status}")
            date_header = response.headers.get("Date")
            if date_header:
                response_headers["Date"] = date_header
            return response.read()

    active_transport = transport or default_transport
    sleeper = sleep or time.sleep
    attempt_count = 0
    while True:
        attempt_count += 1
        try:
            raw = active_transport(url, timeout_seconds)
            break
        except HTTPError as exc:
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt_count >= max_attempts:
                raise
        except (URLError, TimeoutError, ConnectionError):
            if attempt_count >= max_attempts:
                raise
        sleeper(float(retry_backoff_seconds) * (2 ** (attempt_count - 1)))
    if not isinstance(raw, bytes):
        raise ValueError("transport must return raw response bytes")
    retrieved_at = (clock or (lambda: datetime.now(timezone.utc)))()
    if not isinstance(retrieved_at, datetime) or retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieval clock must return a timezone-aware datetime")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Wallex response must be a JSON object")
    candles = parse_history(payload, symbol=symbol, timeframe_minutes=timeframe_minutes, as_of=as_of)
    server_date_header = response_headers.get("Date")
    server_clock_offset_seconds = None
    if server_date_header:
        server_date = parsedate_to_datetime(server_date_header)
        if server_date.tzinfo is None:
            server_date = server_date.replace(tzinfo=timezone.utc)
        server_clock_offset_seconds = (server_date.astimezone(timezone.utc) - retrieved_at.astimezone(timezone.utc)).total_seconds()
    return NativeFetchEvidence(
        request_url=url,
        retrieved_at=retrieved_at.astimezone(timezone.utc),
        raw_response=raw,
        raw_sha256=sha256(raw).hexdigest(),
        server_date_header=server_date_header,
        server_clock_offset_seconds=server_clock_offset_seconds,
        attempt_count=attempt_count,
        candles=candles,
    )


def fetch_native_ohlcv(
    *,
    symbol: str,
    timeframe_minutes: int,
    start: datetime,
    end: datetime,
    as_of: datetime,
    timeout_seconds: float = 10.0,
    transport: Callable[[str, float], bytes] | None = None,
    max_attempts: int = 3,
    retry_backoff_seconds: float = 0.25,
    sleep: Callable[[float], None] | None = None,
) -> tuple[NativeCandle, ...]:
    """Compatibility wrapper returning only parsed candles."""
    return fetch_native_ohlcv_evidence(
        symbol=symbol,
        timeframe_minutes=timeframe_minutes,
        start=start,
        end=end,
        as_of=as_of,
        timeout_seconds=timeout_seconds,
        transport=transport,
        max_attempts=max_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        sleep=sleep,
    ).candles
