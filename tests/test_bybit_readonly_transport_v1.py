import hashlib
import json
import pytest
from forward.bybit_readonly_transport_v1 import BybitReadOnlyTransportV1, WS_URL

class FakeWS:
    def __init__(self,url,on_open,on_message):
        self.url,self.on_open,self.on_message=url,on_open,on_message
        self.sent=[]; self.kwargs={}
    def send(self,v): self.sent.append(v)
    def close(self): pass
    def run_forever(self,**kwargs):
        self.kwargs=kwargs; self.on_open(self)
        self.on_message(self,json.dumps({"topic":"publicTrade.BTCUSDT","data":[{"s":"BTCUSDT","seq":123}]}))
        self.on_message(self,json.dumps({"topic":"kline.1.BTCUSDT","data":[{"confirm":False}]}))
        self.on_message(self,json.dumps({"op":"subscribe","success":True}))
        self.on_message(self,json.dumps({"topic":"publicTrade.ETHUSDT","data":[{"s":"ETHUSDT"}]}))

def test_public_subscriptions_and_fingerprints():
    out=[]; holder={}
    def factory(*a,**k): holder["ws"]=FakeWS(*a,**k); return holder["ws"]
    t=BybitReadOnlyTransportV1(on_frame=out.append,ws_factory=factory); t.run_once()
    assert holder["ws"].url==WS_URL
    assert json.loads(holder["ws"].sent[0])=={"op":"subscribe","args":["publicTrade.BTCUSDT","kline.1.BTCUSDT"]}
    assert [x["topic"] for x in out]==["publicTrade.BTCUSDT","kline.1.BTCUSDT"]
    assert all(len(x["raw_frame_sha256"])==64 for x in out)
    assert t.ignored==1 and t.rejected==1
    assert holder["ws"].kwargs=={"ping_interval":20,"ping_timeout":10}

def test_budget_must_be_positive():
    with pytest.raises(ValueError,match="max_runtime_seconds"):
        BybitReadOnlyTransportV1(on_frame=lambda _:None,ws_factory=FakeWS,max_runtime_seconds=0)

def test_only_official_endpoint_allowed():
    with pytest.raises(ValueError,match="official Bybit"):
        BybitReadOnlyTransportV1(on_frame=lambda _:None,ws_factory=FakeWS,url="wss://example.invalid")

def test_interval_allowlist():
    with pytest.raises(ValueError,match="interval"):
        BybitReadOnlyTransportV1(on_frame=lambda _:None,ws_factory=FakeWS,interval="2")

def test_hash_is_exact_raw_bytes():
    raw=json.dumps({"topic":"publicTrade.BTCUSDT","data":[{"s":"BTCUSDT"}]}); out=[]
    class One(FakeWS):
        def run_forever(self,**kwargs): self.on_open(self); self.on_message(self,raw)
    BybitReadOnlyTransportV1(on_frame=out.append,ws_factory=lambda *a,**k:One(*a,**k)).run_once()
    assert out[0]["raw_frame_sha256"]==hashlib.sha256(raw.encode()).hexdigest()
