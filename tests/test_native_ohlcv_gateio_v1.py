from __future__ import annotations
import hashlib, json
from decimal import Decimal
import pytest
from forward.native_ohlcv_gateio_v1 import GateioSpotKlineSource

BASE_S=1_800_000_000
STEP=900

def row(ts, *, close="100.25", base="2.50", quote="250.625"):
    return [str(ts),quote,close,"102.00","99.00","100.00",base,"true"]

def make_source(rows, *, fetched_ms=BASE_S*1000+STEP*1000*5):
    body=json.dumps(rows,separators=(",",":")).encode()
    return GateioSpotKlineSource(transport=lambda _url,_timeout: body,clock_ms=lambda:fetched_ms),body

def test_gateio_maps_to_canonical_batch_and_preserves_unknown_flow_as_unavailable():
    source,body=make_source([row(BASE_S+STEP),row(BASE_S)])
    batch=source.fetch(symbol="BTCUSDT",interval="15m",limit=10)
    assert batch.venue=="gateio" and batch.product=="spot" and batch.symbol=="BTCUSDT"
    assert batch.endpoint_kind=="spot_candlesticks"
    assert batch.response_sha256==hashlib.sha256(body).hexdigest()
    assert [c.open_time_ms for c in batch.candles]==[BASE_S*1000,(BASE_S+STEP)*1000]
    c=batch.candles[0]
    assert c.open==Decimal("100.00") and c.volume==Decimal("2.50") and c.quote_volume==Decimal("250.625")
    assert c.trade_count is None and c.taker_buy_volume is None and c.taker_buy_quote_volume is None

def test_open_candle_is_excluded_and_counted():
    now=(BASE_S+STEP)*1000+10_000
    source,body=make_source([row(BASE_S+STEP),row(BASE_S)],fetched_ms=now)
    batch=source.fetch(symbol="BTCUSDT",interval="15m",limit=10,as_of_ms=now)
    assert len(batch.candles)==1 and batch.candles[0].open_time_ms==BASE_S*1000
    assert batch.open_candles_excluded==1

def test_gaps_are_reported_not_filled():
    source,_=make_source([row(BASE_S+3*STEP),row(BASE_S)])
    batch=source.fetch(symbol="BTCUSDT",interval="15m",limit=10)
    assert len(batch.candles)==2 and len(batch.gaps)==1 and batch.gaps[0].missing_intervals==2

def test_conflicting_duplicates_and_bad_identity_fail_closed():
    source,_=make_source([row(BASE_S),row(BASE_S,close="100.26")])
    with pytest.raises(ValueError,match="conflicting duplicate"):
        source.fetch(symbol="BTCUSDT",interval="15m",limit=10)
    with pytest.raises(ValueError,match="unsupported Gate.io spot symbol"):
        source.fetch(symbol="BTC-USD",interval="15m",limit=10)

def test_nonfinite_and_invalid_ohlc_rejected():
    source,_=make_source([[str(BASE_S),"NaN","100","102","99","100","2.5"]])
    with pytest.raises(ValueError): source.fetch(symbol="BTCUSDT",interval="15m",limit=10)
    source,_=make_source([[str(BASE_S),"250","100","98","99","100","2.5"]])
    with pytest.raises(ValueError,match="OHLC bounds"): source.fetch(symbol="BTCUSDT",interval="15m",limit=10)

def test_query_uses_gateio_symbol_and_public_endpoint():
    seen=[]
    source=GateioSpotKlineSource(transport=lambda url,_timeout:(seen.append(url) or json.dumps([row(BASE_S)]).encode()),clock_ms=lambda:BASE_S*1000+STEP*1000*2)
    source.fetch(symbol="BTCUSDT",interval="15m",limit=50)
    assert seen[0].startswith("https://api.gateio.ws/api/v4/spot/candlesticks?")
    assert "currency_pair=BTC_USDT" in seen[0] and "interval=15m" in seen[0]

def test_documented_base_quote_volume_features_ready_without_fabricating_taker_flow():
    from forward.native_ohlcv_feature_pipeline_v1 import NativeOHLCVFeaturePipelineV1
    from forward.native_ohlcv_gateio_v1 import (VOLUME_SEMANTICS_APPROVED_FOR_BASE_QUOTE_FEATURES,
        VOLUME_SEMANTICS_CONTRACT_VERSION, VOLUME_SEMANTICS_SOURCE_DOC_URL,
        TRADE_COUNT_AVAILABLE, TAKER_BUY_FLOW_AVAILABLE)
    assert VOLUME_SEMANTICS_APPROVED_FOR_BASE_QUOTE_FEATURES is True
    assert VOLUME_SEMANTICS_CONTRACT_VERSION == "gateio_spot_candlestick_volume_v1"
    assert VOLUME_SEMANTICS_SOURCE_DOC_URL.startswith("https://www.gate.com/docs/")
    assert TRADE_COUNT_AVAILABLE is False and TAKER_BUY_FLOW_AVAILABLE is False
    rows=[]
    for i in range(25):
        ts=BASE_S+i*STEP
        close=str(100+i)
        rows.append([str(ts),str(2.5*(100+i)),close,str(102+i),str(99+i),str(100+i),"2.50","true"])
    now=(BASE_S+30*STEP)*1000
    source,body=make_source(list(reversed(rows)),fetched_ms=now)
    batch=source.fetch(symbol="BTCUSDT",interval="15m",limit=50,as_of_ms=now)
    result=NativeOHLCVFeaturePipelineV1(
        volume_semantics_approved=VOLUME_SEMANTICS_APPROVED_FOR_BASE_QUOTE_FEATURES
    ).build(batch,now_ms=now)
    assert result.decision_ready is True
    assert result.reason=="NATIVE_OHLCV_FEATURES_READY"
    assert result.snapshot is not None
    assert result.snapshot.volume_ratio is not None
    assert result.snapshot.buy_ratio is None
    assert result.snapshot.buy_sell_delta is None

def test_native_batch_rejects_partially_available_taker_flow():
    from dataclasses import replace
    from forward.native_ohlcv_v1 import validate_native_batch
    source,_=make_source([row(BASE_S)])
    batch=source.fetch(symbol="BTCUSDT",interval="15m",limit=10)
    bad_candle=replace(batch.candles[0],taker_buy_volume=Decimal("0.1"),taker_buy_quote_volume=None)
    bad_batch=replace(batch,candles=(bad_candle,))
    with pytest.raises(ValueError,match="both be available or both be unavailable"):
        validate_native_batch(bad_batch)
