from __future__ import annotations

import json
from unittest.mock import patch

import forward.global_market_data_gateio_v1 as feed


class FakeSession:
    def __init__(self):
        self.headers = {}


class FakeSocket:
    def __init__(self, recv):
        self._recv = recv
        self.closed = False
        self.sent = []

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def recv(self):
        return self._recv()

    def close(self):
        self.closed = True


def test_disconnect_closes_socket_before_backoff_then_reconnects_with_rest_backfill():
    original_stop = feed.STOP
    feed.STOP = False

    def fail_first_connection():
        raise ConnectionError("injected_disconnect")

    def subscribe_then_stop():
        feed.STOP = True
        return json.dumps({"event": "subscribe", "result": {"status": "success"}})

    first = FakeSocket(fail_first_connection)
    second = FakeSocket(subscribe_then_stop)
    connections = []
    rest_calls = []
    sleep_calls = []

    def create_connection(*args, **kwargs):
        connections.append((args, kwargs))
        return (first, second)[len(connections) - 1]

    def backfill(session):
        rest_calls.append(True)
        return []

    def sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) == 1:
            assert first.closed, "disconnected socket must close before reconnect backoff"

    try:
        with patch.object(feed.signal, "signal", lambda *args, **kwargs: None), \
             patch.object(feed.requests, "Session", return_value=FakeSession()), \
             patch.object(feed.websocket, "create_connection", side_effect=create_connection), \
             patch.object(feed, "_last_saved_ts", return_value=-1), \
             patch.object(feed, "fetch_recent_closed", side_effect=backfill), \
             patch.object(feed, "_append_new", side_effect=lambda candles, last_ts: last_ts), \
             patch.object(feed.time, "sleep", side_effect=sleep):
            feed.run()
    finally:
        feed.STOP = original_stop

    assert len(connections) == 2
    assert len(rest_calls) == 2
    assert sleep_calls == [2]
    assert first.closed and second.closed
    assert second.sent[0]["channel"] == "spot.candlesticks"
    assert second.sent[0]["payload"] == ["15m", "BTC_USDT"]
