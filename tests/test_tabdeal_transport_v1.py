import json
import threading
from datetime import datetime, timezone

import pytest

from forward.tabdeal_transport_v1 import TabdealReadOnlyTransportV1

ASOF = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)

class FakeWS:
    def __init__(self, url, on_open, on_message):
        self.url = url; self.on_open = on_open; self.on_message = on_message
        self.sent = []; self.closed = False; self.kwargs = {}
    def send(self, x): self.sent.append(x)
    def close(self): self.closed = True
    def run_forever(self, **kwargs):
        self.kwargs = kwargs
        self.on_open(self)
        self.on_message(self, json.dumps({"trade": {"symbol":"BTC_USDT","price":"100","amount":"1","side_name":"buy","sequence":1,"updated":"2026-10-07T06:59:00+00:00"}}))
        self.on_message(self, json.dumps({"order": {"x":1}}))
        self.on_message(self, json.dumps({"trade": {"symbol":"ETH_USDT","price":"100","amount":"1","side_name":"buy","sequence":2,"updated":"2026-10-07T06:59:01+00:00"}}))

def test_transport_only_handoffs_records():
    out=[]; holder={}
    def factory(*args, **kwargs):
        holder["ws"]=FakeWS(*args, **kwargs); return holder["ws"]
    t=TabdealReadOnlyTransportV1(as_of_provider=lambda:ASOF,on_record=out.append,ws_factory=factory)
    t.run_once()
    assert out[0]["source"]=="tabdeal_ws_forward_v1"
    assert t.records_emitted==1; assert t.rejected==1; assert t.rejection_reasons==["ValueError"]
    assert t.ignored==1; assert t.frames_seen==3
    assert holder["ws"].sent==["BTC_USDT"]
    assert holder["ws"].kwargs=={"ping_interval":20,"ping_timeout":10}

def test_transport_rejects_non_positive_runtime():
    with pytest.raises(ValueError, match="max_runtime_seconds"):
        TabdealReadOnlyTransportV1(as_of_provider=lambda:ASOF,on_record=lambda _:None,ws_factory=FakeWS,max_runtime_seconds=0)

def test_transport_budget_closes_socket():
    started=threading.Event(); closed=threading.Event()
    class BlockingWS(FakeWS):
        def close(self): super().close(); closed.set()
        def run_forever(self, **kwargs):
            self.kwargs=kwargs; self.on_open(self); started.set(); closed.wait(timeout=1.0)
    holder={}
    def factory(*args, **kwargs):
        holder["ws"]=BlockingWS(*args, **kwargs); return holder["ws"]
    t=TabdealReadOnlyTransportV1(as_of_provider=lambda:ASOF,on_record=lambda _:None,ws_factory=factory,max_runtime_seconds=0.02)
    t.run_once()
    assert started.is_set(); assert closed.is_set(); assert holder["ws"].closed is True; assert t.closed_by_budget is True
