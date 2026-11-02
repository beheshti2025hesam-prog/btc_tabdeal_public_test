from __future__ import annotations

import json
from pathlib import Path

from forward import global_market_data_gateio_v1 as collector


def candle(ts: int) -> dict:
    return {
        "schema": "hes_global_candle_v1",
        "source": collector.SOURCE,
        "symbol": collector.SYMBOL,
        "timeframe": collector.INTERVAL,
        "open_time": ts,
        "close_time": ts + collector.INTERVAL_SECONDS,
        "open": "100",
        "high": "102",
        "low": "99",
        "close": "101",
        "volume": "1.2",
        "quote_volume": "120",
        "closed": True,
        "observed_at": "2026-11-02T00:00:00+00:00",
    }


def test_disconnect_reconnect_rest_sync_recovers_and_deduplicates(tmp_path, monkeypatch):
    """Exercise the real merge/persist path across a simulated WS disconnect."""
    output = tmp_path / "gateio-candles.jsonl"
    monkeypatch.setattr(collector, "OUTPUT", output)
    # _append_new has a definition-time default path; inject the temp path explicitly.
    real_append = collector._append_new
    monkeypatch.setattr(collector, "_append_new", lambda rows, last_ts: real_append(rows, last_ts, output))
    monkeypatch.setattr(collector, "STOP", False)
    monkeypatch.setattr(collector.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(collector, "GateioSpotKlineSource", lambda: object())
    monkeypatch.setattr(collector.time, "sleep", lambda _seconds: None)

    rest_batches = iter([
        [candle(900), candle(1800)],
        [candle(900), candle(1800), candle(2700)],
        [candle(900), candle(1800), candle(2700)],
    ])
    monkeypatch.setattr(collector, "fetch_recent_closed", lambda _source: next(rest_batches))

    sockets = []

    class FakeWebSocket:
        def __init__(self, number: int):
            self.number = number
            self.closed = False

        def send(self, _payload):
            pass

        def recv(self):
            if self.number == 1:
                raise RuntimeError("simulated transport disconnect")
            raise AssertionError("test should stop before receiving on second socket")

        def close(self):
            self.closed = True

    def connect(*_args, **_kwargs):
        socket = FakeWebSocket(len(sockets) + 1)
        sockets.append(socket)
        if len(sockets) == 2:
            # Stop cleanly after the reconnect path has performed its REST sync.
            collector.STOP = True
        return socket

    monkeypatch.setattr(collector.websocket, "create_connection", connect)

    collector.run()

    persisted = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["open_time"] for row in persisted] == [900, 1800, 2700]
    assert len({row["open_time"] for row in persisted}) == 3
    assert len(sockets) == 2
    assert all(socket.closed for socket in sockets)
