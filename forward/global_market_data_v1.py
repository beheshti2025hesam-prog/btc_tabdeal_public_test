"""Read-only global aggregate crypto candles from Yahoo Finance chart data.
The public endpoint is unofficial and may change without notice. No exchange-specific
execution candles, account credentials, or order endpoints are used here.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://query2.finance.yahoo.com/v8/finance/chart/"
SYMBOLS = {"BTC-USD": "BTC-USD", "ETH-USD": "ETH-USD", "SOL-USD": "SOL-USD"}
INTERVALS = {"1m": (60, "1d"), "5m": (300, "1d"), "15m": (900, "5d"), "60m": (3600, "1mo"), "1d": (86400, "1y")}

class MarketDataError(ValueError):
    """Global market data cannot safely be used."""

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
    if value is None: raise MarketDataError(f"missing_{field}")
    try: result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError): raise MarketDataError(f"invalid_{field}") from None
    if not result.is_finite(): raise MarketDataError(f"invalid_{field}")
    return result

def parse_chart_payload(payload, *, symbol, interval, as_of, max_latest_age=timedelta(minutes=3)):
    if symbol not in SYMBOLS: raise MarketDataError("unsupported_global_symbol")
    if interval not in INTERVALS: raise MarketDataError("unsupported_interval")
    if as_of.tzinfo is None or as_of.utcoffset() is None: raise MarketDataError("as_of_must_be_timezone_aware")
    now=as_of.astimezone(timezone.utc); seconds,_=INTERVALS[interval]; duration=timedelta(seconds=seconds)
    try:
        chart=payload["chart"]
        if chart.get("error"): raise MarketDataError("global_source_error")
        result=chart["result"][0]; timestamps=result["timestamp"]; quote=result["indicators"]["quote"][0]
        arrays=[quote[k] for k in ("open","high","low","close","volume")]
    except (KeyError,IndexError,TypeError):
        raise MarketDataError("malformed_global_chart_payload") from None
    if not isinstance(timestamps,list) or not all(isinstance(a,list) and len(a)==len(timestamps) for a in arrays):
        raise MarketDataError("global_chart_array_length_mismatch")
    candles=[]; seen=set(); previous=None
    for i,stamp in enumerate(timestamps):
        try: start=datetime.fromtimestamp(int(stamp),timezone.utc)
        except (ValueError,TypeError,OverflowError,OSError): raise MarketDataError(f"invalid_timestamp_{i}") from None
        if start in seen: raise MarketDataError("duplicate_candle_open_time")
        if previous is not None and start<=previous: raise MarketDataError("candles_not_strictly_chronological")
        seen.add(start); previous=start; end=start+duration; values=[a[i] for a in arrays]
        if any(v is None for v in values): continue
        op,high,low,close,volume=(_decimal(v,n) for v,n in zip(values,("open","high","low","close","volume")))
        if min(op,high,low,close)<=0 or volume<0 or low>min(op,close) or high<max(op,close) or low>high:
            raise MarketDataError("invalid_ohlc_or_volume")
        if end<=now: candles.append(Candle("yahoo_finance_public_chart_unverified","crypto_usd_reference_unverified",symbol,interval,start,end,op,high,low,close,volume))
    if not candles: raise MarketDataError("no_closed_candles")
    if max_latest_age is not None:
        age=now-candles[-1].close_time
        if max_latest_age.total_seconds()<=0 or age<timedelta(0) or age>max_latest_age: raise MarketDataError("latest_closed_candle_stale")
    return tuple(candles)

def fetch_closed_klines(*, symbol="BTC-USD", interval="1m", limit=240, as_of=None, max_latest_age=None, timeout=8.0, opener=urlopen):
    if symbol not in SYMBOLS: raise MarketDataError("unsupported_global_symbol")
    if interval not in INTERVALS: raise MarketDataError("unsupported_interval")
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=1000: raise MarketDataError("limit_out_of_range")
    if timeout<=0: raise MarketDataError("timeout_must_be_positive")
    seconds,range_name=INTERVALS[interval]
    request=Request(BASE_URL+SYMBOLS[symbol]+"?"+urlencode({"interval":interval,"range":range_name}),
        headers={"Accept":"application/json","User-Agent":"Mozilla/5.0 (compatible; HES-Trade-Agent/1.0)"})
    try:
        with opener(request,timeout=timeout) as response:
            if getattr(response,"status",200)!=200: raise MarketDataError("market_data_http_error")
            payload=json.loads(response.read().decode("utf-8"), parse_float=Decimal)
    except MarketDataError: raise
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,UnicodeDecodeError) as exc:
        raise MarketDataError(f"market_data_unavailable:{type(exc).__name__}") from None
    freshness=max_latest_age if max_latest_age is not None else timedelta(seconds=max(180,seconds*2))
    bars=parse_chart_payload(payload,symbol=symbol,interval=interval,as_of=as_of or datetime.now(timezone.utc),max_latest_age=freshness)
    return bars[-limit:]
