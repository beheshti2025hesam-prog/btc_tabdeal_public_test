import json
from datetime import datetime, timezone

import pytest

from forward.wallex_socketio_transport_v1 import WallexSocketIOTransportV1


class FakeSocket:
    def __init__(self, frames):
        self.frames = list(frames)
        self.sent = []
        self.closed = False
        self.timeout = None

    def recv(self):
        if not self.frames:
            raise TimeoutError("no fake frame")
        return self.frames.pop(0)

    def send(self, payload):
        self.sent.append(payload)

    def settimeout(self, value):
        self.timeout = value

    def close(self):
        self.closed = True


def make_transport(sockets, events, **kwargs):
    return WallexSocketIOTransportV1(
        "BTCUSDT", channels=("trade", "buyDepth", "sellDepth"),
        socket_factory=lambda endpoint, timeout: sockets.pop(0),
        on_event=events.append,
        clock=lambda: datetime(2026, 10, 18, tzinfo=timezone.utc),
        monotonic_ns=lambda: 123456789,
        **kwargs,
    )


def open_frames(engine_sid="engine-1", socketio_sid="socket-1"):
    return [
        "0" + json.dumps({"sid": engine_sid, "upgrades": [], "pingInterval": 20000,
                          "pingTimeout": 5000, "maxPayload": 1000000}),
        "40" + json.dumps({"sid": socketio_sid}),
    ]


def test_connect_uses_engineio_v3_and_socketio_subscribe_packets():
    sock = FakeSocket(open_frames())
    events = []
    transport = make_transport([sock], events)
    session = transport.connect()
    assert session.engine_sid == "engine-1"
    assert session.socketio_sid == "socket-1"
    assert [json.loads(x[2:]) for x in sock.sent if x.startswith("42")] == [
        ["subscribe", {"channel": "BTCUSDT@trade"}],
        ["subscribe", {"channel": "BTCUSDT@buyDepth"}],
        ["subscribe", {"channel": "BTCUSDT@sellDepth"}],
    ]
    assert transport.connected
    transport.close(session)


def test_engineio_ping_during_handshake_is_answered():
    sock = FakeSocket(["2", *open_frames()])
    events = []
    transport = make_transport([sock], events)
    session = transport.connect()
    assert sock.sent[0] == "3"
    transport.close(session)


def test_trade_broadcaster_event_is_preserved_without_inventing_sequence():
    sock = FakeSocket(open_frames())
    events = []
    transport = make_transport([sock], events)
    session = transport.connect()
    data = {"isBuyOrder": True, "price": "81000.10", "quantity": "0.002",
            "timestamp": "2026-10-18T10:00:00Z"}
    raw = "42" + json.dumps(["Broadcaster", "BTCUSDT@trade", data])
    event = transport.process_frame(session, raw)
    assert event is events[0]
    assert event.kind == "trade"
    assert event.raw == raw
    assert len(event.raw_sha256) == 64
    assert not hasattr(event, "sequence")
    transport.close(session)


def test_official_depth_shape_as_indexed_object_is_valid():
    sock = FakeSocket(open_frames())
    events = []
    transport = make_transport([sock], events)
    session = transport.connect()
    data = {"0": {"quantity": 0.2, "price": "81000.1", "sum": 16200.02}}
    raw = "42" + json.dumps(["Broadcaster", "BTCUSDT@buyDepth", data])
    event = transport.process_frame(session, raw)
    assert event is events[0]
    assert event.data["0"]["quantity"] == 0.2
    transport.close(session)


def test_stale_socketio_session_cannot_dispatch_or_close_new_epoch():
    old_sock, new_sock = FakeSocket(open_frames("e1", "s1")), FakeSocket(open_frames("e2", "s2"))
    events = []
    transport = make_transport([old_sock, new_sock], events)
    old = transport.connect()
    new = transport.connect()
    frame = "42" + json.dumps(["Broadcaster", "BTCUSDT@trade", {
        "isBuyOrder": True, "price": "1", "quantity": "1",
        "timestamp": "2026-10-18T10:00:00Z"
    }])
    assert transport.process_frame(old, frame) is None
    assert events == []
    assert transport.connected
    assert transport.close(old) is False
    assert transport.connected
    transport.close(new)


@pytest.mark.parametrize("data", [
    {"isBuyOrder": "true", "price": "1", "quantity": "1", "timestamp": "2026-10-18T10:00:00Z"},
    {"isBuyOrder": True, "price": "NaN", "quantity": "1", "timestamp": "2026-10-18T10:00:00Z"},
    {"isBuyOrder": True, "price": "1", "quantity": "0", "timestamp": "2026-10-18T10:00:00Z"},
])
def test_invalid_trade_data_fails_closed(data):
    sock = FakeSocket(open_frames())
    events = []
    transport = make_transport([sock], events)
    session = transport.connect()
    with pytest.raises(ValueError):
        transport.process_frame(session, "42" + json.dumps(["Broadcaster", "BTCUSDT@trade", data]))
    assert events == []
    transport.close(session)


def test_wrong_event_name_and_channel_are_ignored():
    sock = FakeSocket(open_frames())
    events = []
    transport = make_transport([sock], events)
    session = transport.connect()
    assert transport.process_frame(session, '42["Other", "BTCUSDT@trade", {}]') is None
    assert transport.process_frame(session, '42["Broadcaster", "ETHUSDT@trade", {}]') is None
    assert events == []
    transport.close(session)



def test_socketio_disconnect_frame_marks_current_session_disconnected():
    sock = FakeSocket(open_frames())
    events = []
    transport = make_transport([sock], events)
    session = transport.connect()
    assert transport.process_frame(session, "41") is None
    assert not transport.connected
    assert transport.process_frame(session, "42" + json.dumps([
        "Broadcaster", "BTCUSDT@trade", {
            "isBuyOrder": True, "price": "1", "quantity": "1",
            "timestamp": "2026-10-18T10:00:00Z"
        }
    ])) is None
    assert events == []
    transport.close(session)



def test_socketio_connect_error_marks_session_disconnected():
    sock = FakeSocket(open_frames())
    events = []
    transport = make_transport([sock], events)
    session = transport.connect()
    assert transport.process_frame(session, '44{"message":"unavailable"}') is None
    assert not transport.connected
    assert events == []
    transport.close(session)


def test_invalid_engineio_handshake_closes_socket():
    sock = FakeSocket(["not-open-packet"])
    transport = WallexSocketIOTransportV1(
        "BTCUSDT", socket_factory=lambda endpoint, timeout: sock
    )
    with pytest.raises(ValueError, match="Engine.IO"):
        transport.connect()
    assert sock.closed
    assert not transport.connected
