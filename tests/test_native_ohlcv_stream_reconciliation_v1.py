from __future__ import annotations

import json
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import web.dashboard as dashboard
from forward.native_ohlcv_websocket_v1 import NativeKlineStreamError, parse_kline_event


def stream_payload():
    now=int(time.time()*1000)
    start=(now//60_000-1)*60_000
    k={"t":start,"T":start+59_999,"s":"BTCUSDT","i":"1m",
       "o":"100.10","h":"102.00","l":"99.50","c":"101.20","v":"12.3400",
       "q":"1234.50","n":8,"V":"4.20","Q":"420.00","B":"0","x":True}
    return json.dumps({"e":"kline","E":now,"s":"BTCUSDT","k":k})


def rest_batch(candle):
    return SimpleNamespace(
        venue="binance",product="spot",symbol="BTCUSDT",interval="1m",
        endpoint_kind="klines",fetched_at_ms=int(time.time()*1000),
        response_sha256="a"*64,candles=(candle,),gaps=(),open_candles_excluded=0,
    )


def test_closed_stream_event_is_admitted_only_after_exact_rest_reconciliation():
    event=parse_kline_event(stream_payload(),symbol="BTCUSDT",interval="1m")
    batch=rest_batch(event.candle)
    features=SimpleNamespace(decision_ready=False,reason="INSUFFICIENT_CLOSED_CANDLES")
    with dashboard._CACHE_LOCK:
        dashboard._CACHE.clear()
    with patch("web.dashboard._SOURCE.fetch",return_value=batch), \
         patch("web.dashboard._FEATURES.build",return_value=features):
        observed,feature_result=dashboard._refresh_batch("BTCUSDT","1m",event=event)
    assert observed is batch
    assert feature_result is features
    assert dashboard._CACHE[("BTCUSDT","1m")][0] is batch


def test_stream_rest_field_mismatch_fails_closed_without_cache_write():
    event=parse_kline_event(stream_payload(),symbol="BTCUSDT",interval="1m")
    conflicting=replace(event.candle,close=event.candle.close+1)
    batch=rest_batch(conflicting)
    with dashboard._CACHE_LOCK:
        dashboard._CACHE.clear()
    with patch("web.dashboard._SOURCE.fetch",return_value=batch), \
         patch("web.dashboard._FEATURES.build") as build:
        with pytest.raises(NativeKlineStreamError,match="rest_websocket_candle_field_mismatch"):
            dashboard._refresh_batch("BTCUSDT","1m",event=event)
    build.assert_not_called()
    assert ("BTCUSDT","1m") not in dashboard._CACHE
