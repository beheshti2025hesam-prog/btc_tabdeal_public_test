"""Read-only Gate.io Spot adapter for the canonical NativeOHLCV contract.

Gate.io candle REST rows provide OHLC, base volume and quote volume, but not
trade count or taker-buy flow. Those fields remain None (unavailable), never
fabricated as zero. The feature pipeline's volume-semantics gate must remain
unapproved unless a separate source-specific evidence contract is approved.
"""
from __future__ import annotations
import hashlib, json, time
from decimal import Decimal, InvalidOperation
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .native_ohlcv_v1 import INTERVAL_MS, CandleGap, NativeCandle, NativeOHLCVBatch, validate_native_batch

REST_URL = "https://api.gateio.ws/api/v4/spot/candlesticks"
_SYMBOLS = {"BTCUSDT": "BTC_USDT", "ETHUSDT": "ETH_USDT", "SOLUSDT": "SOL_USDT"}
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
            if not isinstance(row,(list,tuple)) or len(row)<7: raise ValueError("Gate.io candle row must contain at least seven fields")
            if type(row[0]) not in (str,int) or type(row[0]) is bool: raise ValueError("invalid Gate.io candle timestamp")
            try: open_ms=int(row[0])*1000
            except (ValueError,TypeError) as exc: raise ValueError("invalid Gate.io candle timestamp") from exc
            # Gate.io order: timestamp, quote volume, close, high, low, open, base volume.
            quote=_wire_decimal(row[1],"quote_volume"); close=_wire_decimal(row[2],"close")
            high=_wire_decimal(row[3],"high"); low=_wire_decimal(row[4],"low")
            open_=_wire_decimal(row[5],"open"); volume=_wire_decimal(row[6],"volume")
            if open_ms < 0 or open_ms % interval_ms: raise ValueError("misaligned Gate.io candle timestamp")
            if min(open_,high,low,close) <= 0 or min(volume,quote) < 0: raise ValueError("invalid Gate.io OHLCV values")
            if high < max(open_,low,close) or low > min(open_,high,close): raise ValueError("invalid Gate.io OHLC bounds")
            close_ms=open_ms+interval_ms-1
            if open_ms > cutoff: raise ValueError("Gate.io returned a future candle")
            if start_time_ms is not None and open_ms < start_time_ms: continue
            if end_time_ms is not None and open_ms > end_time_ms: continue
            key=(open_ms,close_ms,open_,high,low,close,volume,quote)
            if open_ms in canonical and canonical[open_ms] != key: raise ValueError("conflicting duplicate Gate.io candle")
            canonical[open_ms]=key
        open_excluded = sum(1 for key in canonical.values() if key[1] >= cutoff)
        candles=[]
        for open_ms,close_ms,open_,high,low,close,volume,quote in sorted(canonical.values(),key=lambda x:x[0]):
            if close_ms >= cutoff: continue
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
