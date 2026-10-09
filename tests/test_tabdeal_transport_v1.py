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


def test_transport_emits_sanitized_frame_fingerprint_for_normalized_trade():
    message = json.dumps({
        "trade": {
            "symbol": "BTC_USDT",
            "price": "100",
            "amount": "0.1",
            "side_name": "buy",
            "sequence": 123,
            "updated": "2026-10-07T06:59:00+00:00",
        }
    })
    metadata = []
    records = []

    class OneFrameWS(FakeWS):
        def run_forever(self, **kwargs):
            self.kwargs = kwargs
            self.on_open(self)
            self.on_message(self, message)

    transport = TabdealReadOnlyTransportV1(
        as_of_provider=lambda: ASOF,
        on_record=records.append,
        on_frame_metadata=metadata.append,
        ws_factory=OneFrameWS,
        max_runtime_seconds=1,
    )
    transport.run_once()

    assert len(records) == 1
    assert len(metadata) == 1
    fingerprint = metadata[0]
    assert fingerprint["schema"] == "hes_transport_frame_fingerprint_v1"
    assert fingerprint["raw_frame_sha256"] == hashlib.sha256(message.encode("utf-8")).hexdigest()
    assert fingerprint["sequence_field_path"] == "trade.sequence"
    assert fingerprint["sequence_value"] == 123
    assert fingerprint["sequence_value_type"] == "int"
    assert fingerprint["outer_keys"] == ["trade"]
    assert "price" in fingerprint["trade_keys"]
    assert "amount" in fingerprint["trade_keys"]
    assert "price" not in fingerprint
    assert "amount" not in fingerprint
    assert "raw_frame" not in fingerprint
    assert fingerprint["receive_monotonic_ns"] > 0
