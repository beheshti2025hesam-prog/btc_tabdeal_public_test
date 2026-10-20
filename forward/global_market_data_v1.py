"""Read-only global public candle source, independent from execution venues."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://data-api.binance.vision/api/v3/klines"
INTERVALS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}

class MarketDataError(ValueError):
    """Public market data cannot safely be used."""

@dataclass(frozen=True)
class Candle:
    source: str
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

def _decimal(value, field):
    try: result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError): raise MarketDataError(f"invalid_{field}") from None
    if not result.is_finite(): raise MarketDataError(f"invalid_{field}")
    return result

def parse_closed_klines(rows, *, symbol, interval, as_of, max_latest_age=timedelta(minutes=3)):
    if not isinstance(symbol, str) or not symbol or symbol != symbol.upper():
        raise MarketDataError("symbol_must_be_explicit_uppercase")
    if interval not in INTERVALS: raise MarketDataError("unsupported_interval")
    if as_of.tzinfo is None or as_of.utcoffset() is None: raise MarketDataError("as_of_must_be_timezone_aware")
    now = as_of.astimezone(timezone.utc); duration = timedelta(seconds=INTERVALS[interval])
    result=[]; seen=set(); previous=None
    for i,row in enumerate(rows):
        if not isinstance(row,(list,tuple)) or len(row)<7: raise MarketDataError(f"malformed_kline_{i}")
        try:
            start=datetime.fromtimestamp(int(row[0])/1000,timezone.utc)
            end=datetime.fromtimestamp((int(row[6])+1)/1000,timezone.utc)
        except (ValueError,TypeError,OverflowError,OSError): raise MarketDataError(f"invalid_timestamp_{i}") from None
        if start in seen: raise MarketDataError("duplicate_candle_open_time")
        if previous is not None and start<=previous: raise MarketDataError("candles_not_strictly_chronological")
        if end != start+duration: raise MarketDataError("candle_interval_boundary_mismatch")
        seen.add(start); previous=start
        op,high,low,close,volume=(_decimal(row[n],name) for n,name in ((1,"open"),(2,"high"),(3,"low"),(4,"close"),(5,"volume")))
        if min(op,high,low,close)<=0 or volume<0 or low>min(op,close) or high<max(op,close) or low>high:
            raise MarketDataError("invalid_ohlc_or_volume")
        if end<=now:
            result.append(Candle("binance_public_market_data","spot",symbol,interval,start,end,op,high,low,close,volume))
    if not result: raise MarketDataError("no_closed_candles")
    if max_latest_age is not None:
        age=now-result[-1].close_time
        if max_latest_age.total_seconds()<=0 or age<timedelta(0) or age>max_latest_age:
            raise MarketDataError("latest_closed_candle_stale")
    return tuple(result)

def fetch_closed_klines(*, symbol="BTCUSDT", interval="1m", limit=240, as_of=None,
                         max_latest_age=timedelta(minutes=3), timeout=8.0, opener=urlopen):
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=1000: raise MarketDataError("limit_out_of_range")
    if timeout<=0: raise MarketDataError("timeout_must_be_positive")
    if interval not in INTERVALS: raise MarketDataError("unsupported_interval")
    request=Request(BASE_URL+"?"+urlencode({"symbol":symbol,"interval":interval,"limit":limit}),
                    headers={"Accept":"application/json","User-Agent":"HES-Trade-Agent-readonly/1"})
    try:
        with opener(request,timeout=timeout) as response:
            if getattr(response,"status",200)!=200: raise MarketDataError("market_data_http_error")
            payload=json.loads(response.read().decode("utf-8"))
    except MarketDataError: raise
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,UnicodeDecodeError) as exc:
        raise MarketDataError(f"market_data_unavailable:{type(exc).__name__}") from None
    if not isinstance(payload,list): raise MarketDataError("unexpected_market_data_payload")
    return parse_closed_klines(payload,symbol=symbol,interval=interval,
        as_of=as_of or datetime.now(timezone.utc),max_latest_age=max_latest_age)
