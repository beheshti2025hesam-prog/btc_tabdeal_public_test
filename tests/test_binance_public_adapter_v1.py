import json, pytest
from urllib.error import URLError
from forward.binance_public_adapter_v1 import fetch_closed_klines
def row(o,c,close="101"): return [o,"100","103","99",close,"12",c,"1200",42,"6","600","0"]
class Response:
 status=200
 def __init__(self,raw): self.raw=raw
 def __enter__(self): return self
 def __exit__(self,*a): pass
 def read(self): return self.raw
def fake(raw): return lambda request,timeout=0:Response(raw)
def test_closed_only_hash_timestamp():
 raw=json.dumps([row(0,899999),row(900000,1799999),row(1800000,2699999)]).encode()
 r=fetch_closed_klines("BTCUSDT","15m",3,base_url="https://example.test",now_ms=lambda:2000000,opener=fake(raw))
 assert r.status=="OK" and r.http_status==200 and len(r.raw_sha256)==64 and r.raw_bytes==len(raw)
 assert r.received_at_utc.endswith("Z") and [c.open_time_ms for c in r.candles]==[0,900000]
def test_network_fail_closed():
 def broken(*a,**k): raise URLError("offline")
 r=fetch_closed_klines(opener=broken); assert r.status=="BLOCKED" and r.reason_code=="NETWORK_ERROR" and not r.candles
def test_invalid_json():
 r=fetch_closed_klines(opener=fake(b"no-json")); assert r.reason_code=="INVALID_JSON"
def test_bad_ohlc():
 r=fetch_closed_klines(opener=fake(json.dumps([row(0,899999,"999")]).encode()),now_ms=lambda:999999)
 assert r.reason_code=="INVALID_CANDLE_DATA"
def test_non_monotonic():
 r=fetch_closed_klines(opener=fake(json.dumps([row(0,899999),row(0,1799999)]).encode()),now_ms=lambda:9999999)
 assert r.reason_code=="INVALID_CANDLE_DATA"
@pytest.mark.parametrize("kw",[{"symbol":"BTC USDT"},{"interval":"10m"},{"limit":0},{"limit":1001}])
def test_bad_args(kw):
 with pytest.raises(ValueError): fetch_closed_klines(**kw)
def test_empty_fail_closed():
 r=fetch_closed_klines(opener=fake(b"[]")); assert r.reason_code=="NO_CLOSED_CANDLES"
