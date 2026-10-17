import hashlib
import json

import pytest

from forward.bybit_readonly_transport_v1 import BybitReadOnlyTransportV1, WS_URL


class FakeWS:
    def __init__(self, url, on_open, on_message):
        self.url = url
        self.on_open = on_open
        self.on_message = on_message
        self.sent = []
        self.kwargs = {}
    def send(self, value):
        self.sent.append(value)
    def close(self):
        pass
    def run_forever(self, **kwargs):
        self.kwargs = kwargs
        self.on_open(self)
        self.on_message(self, json.dumps({
            "topic": "publicTrade.BTCUSDT",
            "data": [{"T": 1792195200000, "s": "BTCUSDT", "S": "Buy", "v": "0.01", "p": "60000", "i": "trade-1", "seq": 123}],
            "ts": 1792195200001,
        }))
        self.on_message(self, json.dumps({
            "topic": "kline.1.BTCUSDT",
            "data": [{"start": 1792195200000, "end": 1792195259999, "interval": "1", "open": "60000", "close": "60001", "high": "60002", "low": "59999", "volume": "0.1", "turnover": "6000", "confirm": False, "timestamp": 1792195200001}],
        }))
        self.on_message(self, json.dumps({"op": "subscribe", "success": True}))
        self.on_message(self, json.dumps({"topic": "publicTrade.ETHUSDT", "data": [{"s": "ETHUSDT"}]}))


def test_bybit_transport_subscribes_only_public_trade_and_kline():
    output = []
    holder = {}
    def factory(*args, **kwargs):
        holder["ws"] = FakeWS(*args, **kwargs)
        return holder["ws"]
    t = BybitReadOnlyTransportV1(on_frame=output.append, ws_factory=factory)
    t.run_once()
    assert holder["ws"].url == WS_URL
    assert json.loads(holder["ws"].sent[0]) == {
        "op": "subscribe",
        "args": ["publicTrade.BTCUSDT", "kline.1.BTCUSDT"],
    }
    assert len(output) == 2
    assert [x["topic"] for x in output] == ["publicTrade.BTCUSDT", "kline.1.BTCUSDT"]
    assert all(x["venue"] == "bybit" and x["market"] == "linear" for x in output)
    assert all(len(x["raw_frame_sha256"]) == 64 for x in output)
    assert t.ignored == 1
    assert t.rejected == 1
    assert holder["ws"].kwargs == {"ping_interval": 20, "ping_timeout": 10}


def test_bybit_transport_rejects_non_positive_budget():
    with pytest.raises(ValueError, match="max_runtime_seconds"):
        BybitReadOnlyTransportV1(on_frame=lambda _: None, ws_factory=FakeWS, max_runtime_seconds=0)


def test_bybit_transport_rejects_non_official_endpoint():
    with pytest.raises(ValueError, match="official Bybit"):
        BybitReadOnlyTransportV1(on_frame=lambda _: None, ws_factory=FakeWS, url="wss://example.invalid/ws")


def test_bybit_transport_rejects_unknown_interval():
    with pytest.raises(ValueError, match="interval"):
        BybitReadOnlyTransportV1(on_frame=lambda _: None, ws_factory=FakeWS, interval="2")


def test_raw_fingerprint_matches_exact_frame_bytes():
    raw = json.dumps({"topic": "publicTrade.BTCUSDT", "data": [{"s": "BTCUSDT"}]})
    output = []
    class OneFrameWS(FakeWS):
        def run_forever(self, **kwargs):
            self.on_open(self)
            self.on_message(self, raw)
    t = BybitReadOnlyTransportV1(on_frame=output.append, ws_factory=lambda *a, **k: OneFrameWS(*a, **k))
    t.run_once()
    assert output[0]["raw_frame_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
