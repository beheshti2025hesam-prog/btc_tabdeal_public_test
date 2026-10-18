import json
from datetime import datetime, timezone

import pytest

from forward.wallex_market_data_collector_v1 import WallexMarketDataCollector


class FakeSocket:
    def __init__(self, sid, frames=()):
        self.sid = sid
        self.frames = list(frames)
        self.sent = []
        self.closed = False

    def recv(self):
        if self.sid is not None:
            sid, self.sid = self.sid, None
            return json.dumps({"sid": sid, "upgrades": [], "pingInterval": 20000,
                               "pingTimeout": 30000, "maxPayload": 1048576})
        if not self.frames:
            raise RuntimeError("no fake frame")
        return self.frames.pop(0)

    def send(self, payload):
        self.sent.append(payload)

    def close(self):
        self.closed = True


def make_collector(sockets, events, **kwargs):
    return WallexMarketDataCollector(
        "BTCUSDT",
        channels=("trade", "buyDepth", "sellDepth"),
        socket_factory=lambda endpoint, timeout: sockets.pop(0),
        on_event=events.append,
        clock=lambda: datetime(2026, 10, 18, tzinfo=timezone.utc),
        monotonic_ns=lambda: 123456789,
        **kwargs,
    )


def trade_frame(ts="2026-10-18T10:00:00Z"):
    return json.dumps(["BTCUSDT@trade", {
        "isBuyOrder": True, "price": "81000.10", "quantity": "0.002",
        "timestamp": ts
    }])


def test_connect_waits_for_session_frame_and_subscribes_each_requested_channel():
    sock = FakeSocket("sid-1")
    events = []
    collector = make_collector([sock], events)
    session = collector.connect()
    assert session.server_sid == "sid-1"
    assert [json.loads(x) for x in sock.sent] == [
        ["subscribe", {"channel": "BTCUSDT@trade"}],
        ["subscribe", {"channel": "BTCUSDT@buyDepth"}],
        ["subscribe", {"channel": "BTCUSDT@sellDepth"}],
    ]
    assert events == []


def test_trade_frame_is_preserved_and_hashed_without_inventing_identity():
    sock = FakeSocket("sid-1")
    events = []
    collector = make_collector([sock], events)
    session = collector.connect()
    raw = trade_frame()
    event = collector.process_frame(session, raw)
    assert event is events[0]
    assert event.kind == "trade"
    assert event.data["quantity"] == "0.002"
    assert event.raw == raw
    assert len(event.raw_sha256) == 64
    assert not hasattr(event, "sequence")
    assert event.received_at_utc.tzinfo is not None
    collector.close(session)


def test_old_session_frame_is_rejected_after_reconnect():
    old_socket, new_socket = FakeSocket("sid-old"), FakeSocket("sid-new")
    events = []
    collector = make_collector([old_socket, new_socket], events)
    old = collector.connect()
    new = collector.connect()
    assert new.epoch > old.epoch
    assert collector.process_frame(old, trade_frame()) is None
    assert events == []
    assert collector.process_frame(new, trade_frame()) is not None
    assert len(events) == 1
    assert not collector.close(old)
    assert collector.connected
    assert collector.close(new)
    assert not collector.connected


def test_wrong_symbol_and_unrequested_channel_are_ignored():
    sock = FakeSocket("sid-1")
    events = []
    collector = make_collector([sock], events)
    session = collector.connect()
    assert collector.process_frame(session, json.dumps(["ETHUSDT@trade", {
        "isBuyOrder": True, "price": "1", "quantity": "1",
        "timestamp": "2026-10-18T10:00:00Z"
    }])) is None
    assert collector.process_frame(session, json.dumps(["BTCUSDT@other", {}])) is None
    assert events == []
    collector.close(session)


@pytest.mark.parametrize("frame", [
    "not-json",
    json.dumps(["BTCUSDT@trade", []]),
    json.dumps(["BTCUSDT@trade", {"isBuyOrder": "true", "price": "1",
                                   "quantity": "1", "timestamp": "2026-10-18T10:00:00Z"}]),
    json.dumps(["BTCUSDT@trade", {"isBuyOrder": True, "price": "1"}]),
])
def test_malformed_trade_frames_fail_closed(frame):
    sock = FakeSocket("sid-1")
    events = []
    collector = make_collector([sock], events)
    session = collector.connect()
    with pytest.raises((ValueError, json.JSONDecodeError)):
        collector.process_frame(session, frame)
    assert events == []
    collector.close(session)


def test_initial_frame_without_sid_fails_closed():
    class BadInitialSocket(FakeSocket):
        def recv(self):
            return json.dumps({"upgrades": [], "pingInterval": 20000})

    sock = BadInitialSocket(None)
    collector = WallexMarketDataCollector(
        "BTCUSDT", socket_factory=lambda endpoint, timeout: sock
    )
    with pytest.raises(ValueError, match="sid"):
        collector.connect()
    assert sock.closed
    assert not collector.connected


def test_configuration_rejects_unknown_channels_and_symbols():
    with pytest.raises(ValueError):
        WallexMarketDataCollector("BTC USDT")
    with pytest.raises(ValueError):
        WallexMarketDataCollector("BTCUSDT", channels=("trade", "unknown"))
    with pytest.raises(ValueError):
        WallexMarketDataCollector("BTCUSDT", endpoint="ws://example.invalid")
