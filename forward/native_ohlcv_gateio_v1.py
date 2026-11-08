"""Read-only Gate.io Spot adapter for the canonical NativeOHLCV contract.

Gate.io's official Spot candlestick schema defines field 1 as quote-currency
volume and field 6 as base-currency amount. That source-specific contract
supports base/quote volume features without normalization. Trade count and
taker-buy flow are not returned and remain None (unavailable), never fabricated.
The approval below applies only to documented base/quote volume features.
Official schema: https://www.gate.com/docs/developers/apiv4/en/spot/
"""
from __future__ import annotations
import hashlib, json, time
from types import MappingProxyType
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .native_ohlcv_v1 import INTERVAL_MS, CandleGap, NativeCandle, NativeOHLCVBatch, validate_native_batch

REST_URL = "https://api.gateio.ws/api/v4/spot/candlesticks"
CANDLE_SCHEMA_CONTRACT_VERSION = "gateio_spot_candlestick_v2"
VOLUME_SEMANTICS_CONTRACT_VERSION = "gateio_spot_candlestick_volume_v1"
VOLUME_SEMANTICS_SOURCE_DOC_URL = "https://www.gate.com/docs/developers/apiv4/en/spot/"
VOLUME_SEMANTICS_APPROVED_FOR_BASE_QUOTE_FEATURES = True
TRADE_COUNT_AVAILABLE = False
TAKER_BUY_FLOW_AVAILABLE = False
# One authoritative canonical-symbol -> Gate.io Spot currency-pair mapping.
# Dashboard, persisted-reader boundary and adapter contract must use this same table.
GATEIO_SPOT_SYMBOL_MAP = MappingProxyType({
    "BTCUSDT": "BTC_USDT",
    "ETHUSDT": "ETH_USDT",
    "SOLUSDT": "SOL_USDT",
})
_SYMBOLS = GATEIO_SPOT_SYMBOL_MAP


def gateio_spot_source_symbol(canonical_symbol: str) -> str:
    """Resolve an HES canonical symbol to the exact Gate.io Spot pair."""
    if type(canonical_symbol) is not str or canonical_symbol not in GATEIO_SPOT_SYMBOL_MAP:
        raise ValueError("unsupported Gate.io Spot canonical symbol")
    return GATEIO_SPOT_SYMBOL_MAP[canonical_symbol]


def verify_gateio_spot_symbol_mapping(canonical_symbol: str, source_symbol: str) -> bool:
    """Verify source identity against the authoritative adapter mapping; never infer it."""
    return (type(canonical_symbol) is str and type(source_symbol) is str
            and GATEIO_SPOT_SYMBOL_MAP.get(canonical_symbol) == source_symbol)


def from_persisted_global_rows(rows, *, timeframe: str, now_ms: int) -> NativeOHLCVBatch:
    """Normalize the existing persisted Gate.io reader rows; perform no network I/O.

    The persisted reader stores candle close_time as the exclusive interval boundary
    in seconds. NativeOHLCVBatch stores the final inclusive millisecond, so this
    adapter subtracts one millisecond after validating the exact source contract.
    Its response_sha256 is explicitly the hash of the persisted row set, not a
    fabricated raw HTTP response hash.
    """
    if not isinstance(rows, list) or not rows:
        raise ValueError("persisted Gate.io rows must be a non-empty list")
    if timeframe not in SUPPORTED_INTERVALS or timeframe not in INTERVAL_MS:
        raise ValueError("unsupported persisted Gate.io timeframe")
    if type(now_ms) is not int or now_ms < 0:
        raise ValueError("now_ms must be a non-negative integer")

    interval_ms = INTERVAL_MS[timeframe]
    interval_seconds = interval_ms // 1000
    candles = []
    gaps = []
    previous_open_ms = None
    observed_times = []

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"persisted Gate.io row {index} must be an object")
        if row.get("schema") != "hes_global_candle_v1":
            raise ValueError("persisted Gate.io candle schema mismatch")
        if row.get("source") != "gateio_public_spot":
            raise ValueError("persisted Gate.io source identity mismatch")
        if row.get("symbol") != "BTC_USDT":
            raise ValueError("persisted Gate.io symbol identity mismatch")
        if row.get("timeframe") != timeframe:
            raise ValueError("persisted Gate.io timeframe identity mismatch")
        if row.get("closed") is not True:
            raise ValueError("persisted Gate.io open candle rejected")
        if any(row.get(field) is not None for field in (
            "trade_count", "taker_buy_volume", "taker_buy_quote_volume"
        )):
            raise ValueError("Gate.io trade-flow fields must remain unavailable")

        open_seconds = row.get("open_time")
        close_boundary_seconds = row.get("close_time")
        if type(open_seconds) is not int or type(close_boundary_seconds) is not int:
            raise ValueError("persisted Gate.io candle times must be integer seconds")
        open_ms = open_seconds * 1000
        if open_seconds < 0 or open_ms % interval_ms:
            raise ValueError("persisted Gate.io candle open time is misaligned")
        if close_boundary_seconds != open_seconds + interval_seconds:
            raise ValueError("persisted Gate.io candle close boundary is invalid")
        close_ms = close_boundary_seconds * 1000 - 1
        if close_boundary_seconds * 1000 > now_ms:
            raise ValueError("persisted Gate.io candle close is in the future")

        observed_at = row.get("observed_at")
        if not isinstance(observed_at, str) or not observed_at.strip():
            raise ValueError("persisted Gate.io observation timestamp missing")
        try:
            observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("persisted Gate.io observation timestamp invalid") from exc
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("persisted Gate.io observation timestamp must be timezone-aware")
        observed_ms = int(observed.timestamp() * 1000)
        if observed_ms > now_ms + 60_000:
            raise ValueError("persisted Gate.io observation time is ahead of current UTC")
        observed_times.append(observed_ms)

        open_price = _wire_decimal(row.get("open"), "open")
        high = _wire_decimal(row.get("high"), "high")
        low = _wire_decimal(row.get("low"), "low")
        close = _wire_decimal(row.get("close"), "close")
        volume = _wire_decimal(row.get("volume"), "volume")
        quote_volume = _wire_decimal(row.get("quote_volume"), "quote_volume")
        if min(open_price, high, low, close) <= 0 or min(volume, quote_volume) < 0:
            raise ValueError("persisted Gate.io OHLCV values are outside valid bounds")
        if high < max(open_price, low, close) or low > min(open_price, high, close):
            raise ValueError("persisted Gate.io OHLC geometry is invalid")

        if previous_open_ms is not None:
            distance = open_ms - previous_open_ms
            if distance <= 0:
                raise ValueError("persisted Gate.io candles are duplicate or unordered")
            if distance > interval_ms:
                gaps.append(CandleGap(
                    expected_open_time_ms=previous_open_ms + interval_ms,
                    next_observed_open_time_ms=open_ms,
                    missing_intervals=(distance // interval_ms) - 1,
                ))
        candles.append(NativeCandle(
            venue="gateio", product="spot", symbol="BTCUSDT", interval=timeframe,
            open_time_ms=open_ms, close_time_ms=close_ms,
            open=open_price, high=high, low=low, close=close,
            volume=volume, quote_volume=quote_volume,
            trade_count=None, taker_buy_volume=None, taker_buy_quote_volume=None,
            closed=True,
        ))
        previous_open_ms = open_ms

    if observed_times and max(observed_times) > now_ms + 60_000:
        raise ValueError("persisted Gate.io observation time is ahead of current UTC")
    latest_close_boundary_ms = rows[-1]["close_time"] * 1000
    if now_ms - latest_close_boundary_ms > 2 * interval_ms:
        raise ValueError("persisted Gate.io candle feed is stale")
    # fetched_at_ms is when this adapter read the persisted feed, not when the
    # exchange originally emitted each candle. Per-row observed_at stays bound
    # inside the persisted-row digest above.
    fetched_at_ms = now_ms
    try:
        canonical_rows = json.dumps(
            rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("persisted Gate.io rows are not canonical JSON") from exc
    batch = NativeOHLCVBatch(
        venue="gateio", product="spot", symbol="BTCUSDT", interval=timeframe,
        endpoint_kind="global_market_data_reader_v1", fetched_at_ms=fetched_at_ms,
        response_sha256=hashlib.sha256(canonical_rows).hexdigest(),
        candles=tuple(candles), gaps=tuple(gaps), open_candles_excluded=0,
    )
    validate_native_batch(batch)
    return batch
SUPPORTED_INTERVALS = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})
_TIMEOUT = 10

def _get(url: str, timeout: int) -> bytes:
    req = Request(url, headers={"Accept":"application/json", "User-Agent":"HES-Native-OHLCV/1.0"}, method="GET")
    with urlopen(req, timeout=timeout) as response:
        if response.status != 200: raise RuntimeError(f"Gate.io public candles returned HTTP {response.status}")
        return response.read()

def _wire_decimal(value: object, field: str) -> Decimal:
    if type(value) is not str: raise ValueError(f"{field} must be a decimal string")
    try: result=Decimal(value)
    except (InvalidOperation, ValueError) as exc: raise ValueError(f"{field} is not decimal") from exc
    if not result.is_finite(): raise ValueError(f"{field} must be finite")
    return result

class GateioSpotKlineSource:
    venue = "gateio"
    product = "spot"
    def __init__(self, *, transport: Callable[[str,int],bytes] | None = None,
                 clock_ms: Callable[[],int] | None = None) -> None:
        self._transport=transport or _get
        self._clock_ms=clock_ms or (lambda: int(time.time()*1000))
    def fetch(self, *, symbol: str, interval: str="15m", limit: int=100,
              start_time_ms: int|None=None, end_time_ms: int|None=None,
              as_of_ms: int|None=None) -> NativeOHLCVBatch:
        if symbol not in _SYMBOLS: raise ValueError("unsupported Gate.io spot symbol")
        if interval not in SUPPORTED_INTERVALS or interval not in INTERVAL_MS: raise ValueError("unsupported Gate.io interval")
        if type(limit) is not int or not 1 <= limit <= 1000: raise ValueError("limit must be between 1 and 1000")
        for name,value in (("start_time_ms",start_time_ms),("end_time_ms",end_time_ms)):
            if value is not None and (type(value) is not int or value < 0): raise ValueError(f"{name} must be a non-negative integer")
        if start_time_ms is not None and end_time_ms is not None and start_time_ms > end_time_ms: raise ValueError("start time exceeds end time")
        params={"currency_pair":_SYMBOLS[symbol],"interval":interval,"limit":limit}
        if start_time_ms is not None: params["from"]=start_time_ms//1000
        if end_time_ms is not None: params["to"]=end_time_ms//1000
        body=self._transport(REST_URL+"?"+urlencode(params),_TIMEOUT)
        if type(body) is not bytes: raise ValueError("transport must return raw response bytes")
        digest=hashlib.sha256(body).hexdigest()
        try: rows=json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise ValueError("invalid Gate.io JSON") from exc
        if not isinstance(rows,list): raise ValueError("Gate.io candle response must be a list")
        fetched=self._clock_ms()
        if type(fetched) is not int or fetched < 0: raise ValueError("clock must return non-negative milliseconds")
        if as_of_ms is not None and (type(as_of_ms) is not int or as_of_ms < 0 or as_of_ms > fetched): raise ValueError("invalid as_of_ms")
        cutoff=fetched if as_of_ms is None else as_of_ms
        interval_ms=INTERVAL_MS[interval]
        canonical={}; open_excluded=0
        for row in rows:
            if not isinstance(row,(list,tuple)) or len(row) != 8: raise ValueError("Gate.io candle row must contain exactly eight documented fields")
            if type(row[0]) not in (str,int) or type(row[0]) is bool: raise ValueError("invalid Gate.io candle timestamp")
            try: open_ms=int(row[0])*1000
            except (ValueError,TypeError) as exc: raise ValueError("invalid Gate.io candle timestamp") from exc
            # Gate.io order: timestamp, quote volume, close, high, low, open,
            # base volume, closed-window flag.
            quote=_wire_decimal(row[1],"quote_volume"); close=_wire_decimal(row[2],"close")
            high=_wire_decimal(row[3],"high"); low=_wire_decimal(row[4],"low")
            open_=_wire_decimal(row[5],"open"); volume=_wire_decimal(row[6],"volume")
            if row[7] not in ("true", "false"): raise ValueError("invalid Gate.io closed-window flag")
            venue_closed = row[7] == "true"
            if open_ms < 0 or open_ms % interval_ms: raise ValueError("misaligned Gate.io candle timestamp")
            if min(open_,high,low,close) <= 0 or min(volume,quote) < 0: raise ValueError("invalid Gate.io OHLCV values")
            if high < max(open_,low,close) or low > min(open_,high,close): raise ValueError("invalid Gate.io OHLC bounds")
            close_ms=open_ms+interval_ms-1
            if open_ms > cutoff: raise ValueError("Gate.io returned a future candle")
            if start_time_ms is not None and open_ms < start_time_ms: continue
            if end_time_ms is not None and open_ms > end_time_ms: continue
            key=(open_ms,close_ms,open_,high,low,close,volume,quote,venue_closed)
            if open_ms in canonical and canonical[open_ms] != key: raise ValueError("conflicting duplicate Gate.io candle")
            canonical[open_ms]=key
        open_excluded = sum(1 for key in canonical.values() if key[1] >= cutoff or not key[8])
        candles=[]
        for open_ms,close_ms,open_,high,low,close,volume,quote,venue_closed in sorted(canonical.values(),key=lambda x:x[0]):
            if not venue_closed or close_ms >= cutoff: continue
            candles.append(NativeCandle(venue=self.venue,product=self.product,symbol=symbol,interval=interval,
                open_time_ms=open_ms,close_time_ms=close_ms,open=open_,high=high,low=low,close=close,
                volume=volume,quote_volume=quote,trade_count=None,taker_buy_volume=None,taker_buy_quote_volume=None,closed=True))
        gaps=[]
        for prev,current in zip(candles,candles[1:]):
            distance=current.open_time_ms-prev.open_time_ms
            if distance>interval_ms: gaps.append(CandleGap(prev.open_time_ms+interval_ms,current.open_time_ms,distance//interval_ms-1))
            elif distance<interval_ms: raise ValueError("overlapping Gate.io candle intervals")
        batch=NativeOHLCVBatch(venue=self.venue,product=self.product,symbol=symbol,interval=interval,
            endpoint_kind="spot_candlesticks",fetched_at_ms=fetched,response_sha256=digest,
            candles=tuple(candles),gaps=tuple(gaps),open_candles_excluded=open_excluded)
        validate_native_batch(batch)
        return batch
