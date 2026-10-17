"""Read-only Wallex native OHLCV adapter (contract v1).

This module calls the documented public /v1/udf/history endpoint. It does not
place orders, use account credentials, synthesize candles from trades, or infer
missing candles. Only candles whose full interval has ended by as_of are
returned. Unknown/malformed source data fails closed.

Live resolution probes currently support only 1-minute, 1-hour and daily bars.
The endpoint has returned minute bars for resolution=15, hourly bars for
resolution=720, and error statuses for 5/180/360. Do not label those responses
as their requested intervals.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://api.wallex.ir"
ENDPOINT = "/v1/udf/history"
# Only empirically verified buckets. Never accept documented-but-misbehaving
# resolutions until the returned bar spacing is independently verified.
RESOLUTION_SECONDS = {"1": 60, "60": 3600, "1D": 86400}


class WallexCandleError(ValueError):
    """The source response cannot safely be interpreted as native candles."""


@dataclass(frozen=True)
class NativeCandle:
    venue: str
    symbol: str
    resolution: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source_timestamp: int
    source_observed_at: datetime

    @property
    def is_closed(self) -> bool:
        return True


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise WallexCandleError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _decimal(value: Any, field: str, index: int) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise WallexCandleError(f"{field}[{index}] is not a decimal value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise WallexCandleError(f"{field}[{index}] is not a decimal value") from None
    if not result.is_finite():
        raise WallexCandleError(f"{field}[{index}] must be finite")
    return result


def parse_history(payload: Any, *, symbol: str, resolution: str,
                  as_of: datetime, observed_at: datetime) -> tuple[NativeCandle, ...]:
    """Validate a UDF history payload and return only fully closed candles.

    t is the documented candle open-time (Unix seconds). Gaps remain gaps;
    no placeholder bars are created. Identical duplicate timestamps collapse,
    while conflicting duplicates and unsorted timestamps are rejected.
    """
    if not symbol or symbol.strip() != symbol:
        raise WallexCandleError("symbol must be a non-empty trimmed string")
    if resolution not in RESOLUTION_SECONDS:
        raise WallexCandleError(f"unsupported resolution: {resolution}")
    as_of = _utc(as_of, "as_of")
    observed_at = _utc(observed_at, "observed_at")
    if not isinstance(payload, dict):
        raise WallexCandleError("history response must be a JSON object")
    status = payload.get("s")
    if status != "ok":
        raise WallexCandleError(f"source status is not ok: {status!r}")
    fields = ("t", "o", "h", "l", "c", "v")
    arrays = {field: payload.get(field) for field in fields}
    if any(not isinstance(value, list) for value in arrays.values()):
        raise WallexCandleError("history response requires list fields t/o/h/l/c/v")
    lengths = {len(value) for value in arrays.values()}
    if len(lengths) != 1:
        raise WallexCandleError("history arrays have unequal lengths")
    step = RESOLUTION_SECONDS[resolution]
    candles: list[NativeCandle] = []
    previous_timestamp: int | None = None
    seen: dict[int, tuple[Decimal, Decimal, Decimal, Decimal, Decimal]] = {}
    for i, raw_ts in enumerate(arrays["t"]):
        if isinstance(raw_ts, bool) or not isinstance(raw_ts, int):
            raise WallexCandleError(f"t[{i}] must be an integer Unix timestamp")
        ts = raw_ts
        # Wallex's daily session boundary is not specified as UTC midnight.
        # The daily bucket length is used conservatively; alignment is not assumed.
        if resolution != "1D" and ts % step != 0:
            raise WallexCandleError(f"t[{i}] is not aligned to resolution {resolution}")
        if previous_timestamp is not None and ts < previous_timestamp:
            raise WallexCandleError("source candle timestamps are not monotonic")
        values = tuple(_decimal(arrays[k][i], k, i) for k in ("o", "h", "l", "c", "v"))
        op, hi, lo, cl, vol = values
        if op <= 0 or hi <= 0 or lo <= 0 or cl <= 0 or vol < 0:
            raise WallexCandleError(f"candle[{i}] has non-positive price or negative volume")
        if lo > min(op, cl) or hi < max(op, cl) or lo > hi:
            raise WallexCandleError(f"candle[{i}] violates OHLC bounds")
        if ts in seen:
            if seen[ts] != values:
                raise WallexCandleError(f"conflicting duplicate candle timestamp: {ts}")
            previous_timestamp = ts
            continue
        seen[ts] = values
        previous_timestamp = ts
        open_time = datetime.fromtimestamp(ts, timezone.utc)
        close_time = open_time + timedelta(seconds=step)
        if close_time <= as_of:
            candles.append(NativeCandle("wallex", symbol, resolution, open_time,
                close_time, op, hi, lo, cl, vol, ts, observed_at))
    return tuple(candles)


def fetch_history(symbol: str, resolution: str, start: datetime, end: datetime,
                  *, timeout: float = 10.0, as_of: datetime | None = None) -> tuple[NativeCandle, ...]:
    """Fetch a bounded public history range. No credentials or order methods."""
    start = _utc(start, "start")
    end = _utc(end, "end")
    if end <= start:
        raise WallexCandleError("end must be later than start")
    if resolution not in RESOLUTION_SECONDS:
        raise WallexCandleError(f"unsupported resolution: {resolution}")
    params = urlencode({"symbol": symbol, "resolution": resolution,
                        "from": int(start.timestamp()), "to": int(end.timestamp())})
    request = Request(BASE_URL + ENDPOINT + "?" + params,
                      headers={"Accept": "application/json", "User-Agent": "HES-readonly-candles/1.0"})
    received_at = datetime.now(timezone.utc)
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise WallexCandleError(f"HTTP status {response.status}")
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise WallexCandleError("history response exceeds 2 MB safety bound")
            received_at = datetime.now(timezone.utc)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise WallexCandleError(f"history request failed: {type(exc).__name__}") from None
    try:
        payload = json.loads(raw, parse_float=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise WallexCandleError("history response is not valid JSON") from None
    return parse_history(payload, symbol=symbol, resolution=resolution,
                         as_of=as_of or received_at, observed_at=received_at)
