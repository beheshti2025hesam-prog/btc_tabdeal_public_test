from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from forward import global_market_data_gateio_v1 as collector


def ws_row(ts=900, *, quote="2.4", close="12", high="13", low="10", open_="11", volume="1.2"):
    return [str(ts), quote, close, high, low, open_, volume]


def persisted_row(ts=900, *, close="12"):
    return {
        "schema": "hes_global_candle_v1",
        "source": collector.SOURCE,
        "symbol": collector.SYMBOL,
        "timeframe": collector.INTERVAL,
        "open_time": ts,
        "close_time": ts + collector.INTERVAL_SECONDS,
        "open": "11",
        "high": "13",
        "low": "10",
        "close": close,
        "volume": "1.2",
        "quote_volume": "2.4",
        "closed": True,
        "observed_at": "2026-11-02T00:00:00+00:00",
    }


def write_rows(path: Path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def test_normalize_closed_ws_candle():
    candle = collector.normalize_row(ws_row(), now=1800)
    assert candle["open_time"] == 900
    assert candle["close_time"] == 1800
    assert candle["open"] == "11"
    assert candle["close"] == "12"
    assert candle["closed"] is True


def test_open_ws_candle_is_not_persistable():
    assert collector.normalize_row(ws_row(), now=1799)["closed"] is False


def test_reject_bad_ohlc_and_misaligned_timestamp():
    with pytest.raises(ValueError):
        collector.normalize_row(ws_row(high="11"), now=1800)
    with pytest.raises(ValueError):
        collector.normalize_row(ws_row(ts=1000), now=1800)


def test_reject_short_ws_row():
    with pytest.raises(ValueError):
        collector.normalize_row(["900", "2.4"], now=1800)


def test_ws_preserves_distinct_base_and_quote_volumes():
    message = {
        "channel": "spot.candlesticks",
        "event": "update",
        "result": {"n": "15m_BTC_USDT", "t": "900", "v": "2400", "a": "0.03", "c": "12", "h": "13", "l": "10", "o": "11"},
    }
    candle = collector.normalize_ws_message(message, now=1800)
    assert candle is not None
    assert candle["quote_volume"] == "2400"
    assert candle["volume"] == "0.03"


def test_ws_missing_base_volume_is_rejected_not_substituted():
    message = {
        "channel": "spot.candlesticks",
        "event": "update",
        "result": {"n": "15m_BTC_USDT", "t": "900", "v": "2400", "c": "12", "h": "13", "l": "10", "o": "11"},
    }
    assert collector.normalize_ws_message(message, now=1800) is None


def test_rest_fetch_reuses_native_gateio_adapter_and_persists_explicit_symbol_mapping():
    native = SimpleNamespace(
        open_time_ms=900_000,
        close_time_ms=1_799_999,
        open=Decimal("11"), high=Decimal("13"), low=Decimal("10"), close=Decimal("12"),
        volume=Decimal("1.2"), quote_volume=Decimal("2.4"), closed=True,
    )
    batch = SimpleNamespace(fetched_at_ms=1_900_000, gaps=(), candles=(native,))

    class FakeSource:
        def __init__(self):
            self.kwargs = None
        def fetch(self, **kwargs):
            self.kwargs = kwargs
            return batch

    source = FakeSource()
    rows = collector.fetch_recent_closed(source)
    assert source.kwargs == {"symbol": "BTCUSDT", "interval": collector.INTERVAL, "limit": 500}
    assert rows[0]["symbol"] == "BTC_USDT"
    assert rows[0]["open_time"] == 900
    assert rows[0]["close_time"] == 1800
    assert rows[0]["closed"] is True


def test_rest_backfill_fails_closed_when_native_adapter_reports_gaps():
    class FakeSource:
        def fetch(self, **kwargs):
            return SimpleNamespace(fetched_at_ms=1_900_000, gaps=(object(),), candles=())
    with pytest.raises(ValueError, match="gap"):
        collector.fetch_recent_closed(FakeSource())


def test_idempotent_merge_does_not_duplicate_candles(tmp_path):
    path = tmp_path / "candles.jsonl"
    candle = persisted_row()
    assert collector._append_new([candle], -1, path) == 900
    assert collector._append_new([candle], 900, path) == 900
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_decimal_formatting_only_duplicate_is_idempotent_without_rewrite(tmp_path):
    path = tmp_path / "candles.jsonl"
    stored = persisted_row()
    write_rows(path, [stored])
    before = path.read_bytes()

    rest = persisted_row()
    rest["volume"] = "1.20000000"
    rest["quote_volume"] = "2.40000000"

    assert collector._append_new([rest], 900, path) == 900
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("field", "different_value"),
    [
        ("volume", "1.20000001"),
        ("quote_volume", "2.40000001"),
    ],
)
def test_real_base_or_quote_volume_difference_remains_conflict(tmp_path, field, different_value):
    path = tmp_path / "candles.jsonl"
    write_rows(path, [persisted_row()])
    before = path.read_bytes()
    changed = persisted_row()
    changed[field] = different_value

    with pytest.raises(ValueError, match="Conflicting"):
        collector._append_new([changed], 900, path)

    assert path.read_bytes() == before


def test_rest_reconciliation_repairs_a_missing_recent_candle(tmp_path):
    path = tmp_path / "candles.jsonl"
    write_rows(path, [persisted_row(900), persisted_row(2700)])
    result = collector._append_new([persisted_row(900), persisted_row(1800), persisted_row(2700)], 2700, path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert result == 2700
    assert [row["open_time"] for row in rows] == [900, 1800, 2700]


def test_unresolved_gap_fails_closed_without_replacing_last_good_file(tmp_path):
    path = tmp_path / "candles.jsonl"
    write_rows(path, [persisted_row(900), persisted_row(2700)])
    before = path.read_bytes()
    with pytest.raises(ValueError, match="gap"):
        collector._append_new([persisted_row(900), persisted_row(2700)], 2700, path)
    assert path.read_bytes() == before


def test_conflicting_duplicate_fails_closed_without_replacing_last_good_file(tmp_path):
    path = tmp_path / "candles.jsonl"
    write_rows(path, [persisted_row(900)])
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Conflicting"):
        collector._append_new([persisted_row(900, close="12.5")], 900, path)
    assert path.read_bytes() == before

def test_conflicting_existing_duplicate_fails_closed(tmp_path):
    path = tmp_path / "candles.jsonl"
    write_rows(path, [persisted_row(900), persisted_row(900, close="12.5")])
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Conflicting"):
        collector._append_new([], 900, path)
    assert path.read_bytes() == before


def test_run_reconnects_after_disconnect_with_bounded_backoff(monkeypatch):
    connections = []
    sleeps = []

    class FakeWebSocket:
        def __init__(self):
            self.closed = False
        def send(self, _payload):
            pass
        def recv(self):
            raise RuntimeError("simulated WebSocket disconnect")
        def close(self):
            self.closed = True

    def create_connection(*_args, **_kwargs):
        socket = FakeWebSocket()
        connections.append(socket)
        if len(connections) == 2:
            collector.STOP = True
        return socket

    monkeypatch.setattr(collector, "STOP", False)
    monkeypatch.setattr(collector.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(collector, "GateioSpotKlineSource", lambda: object())
    monkeypatch.setattr(collector, "_last_saved_ts", lambda _path: -1)
    monkeypatch.setattr(collector, "fetch_recent_closed", lambda _source: [])
    monkeypatch.setattr(collector, "_append_new", lambda _candles, last_ts: last_ts)
    monkeypatch.setattr(collector.websocket, "create_connection", create_connection)
    monkeypatch.setattr(collector.time, "sleep", lambda seconds: sleeps.append(seconds))

    collector.run()

    assert len(connections) == 2
    assert sleeps == [2]
    assert all(socket.closed for socket in connections)

def test_persisted_window_is_capped_at_native_adapter_limit(tmp_path):
    path = tmp_path / "candles.jsonl"
    rows = [persisted_row(900 + index * collector.INTERVAL_SECONDS) for index in range(501)]
    assert collector._append_new(rows, -1, path) == rows[-1]["open_time"]
    persisted = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(persisted) == collector.MAX_PERSISTED_CANDLES == 500
    assert persisted[0]["open_time"] == rows[1]["open_time"]

def test_closed_ws_message_triggers_rest_persistence_only(monkeypatch):
    rest_rows = [persisted_row(900)]
    appended = []

    class FakeWebSocket:
        def __init__(self):
            self.messages = [
                json.dumps({"event": "subscribe", "result": {"status": "success"}}),
                json.dumps({
                    "channel": "spot.candlesticks", "event": "update",
                    "result": {"n": "15m_BTC_USDT", "t": "900", "v": "2.4", "a": "1.2", "c": "12", "h": "13", "l": "10", "o": "11"},
                }),
            ]
            self.closed = False
        def send(self, _payload):
            pass
        def recv(self):
            if self.messages:
                message = self.messages.pop(0)
                if not self.messages:
                    collector.STOP = True
                return message
            raise RuntimeError("unexpected extra recv")
        def close(self):
            self.closed = True

    socket = FakeWebSocket()
    monkeypatch.setattr(collector, "STOP", False)
    monkeypatch.setattr(collector.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(collector, "GateioSpotKlineSource", lambda: object())
    monkeypatch.setattr(collector, "_last_saved_ts", lambda _path: -1)
    monkeypatch.setattr(collector, "fetch_recent_closed", lambda _source: rest_rows)
    monkeypatch.setattr(collector, "_append_new", lambda rows, last_ts: appended.append(rows) or last_ts)
    monkeypatch.setattr(collector.websocket, "create_connection", lambda *_args, **_kwargs: socket)

    collector.run()

    assert appended == [rest_rows, rest_rows]
    assert socket.closed is True


def test_default_collector_paths_are_repository_relative():
    expected_root = Path(__file__).resolve().parents[2]
    assert collector.ROOT == expected_root
    assert collector.DEFAULT_OUTPUTS["15m"] == expected_root / "data/forward/global_market_candles_v1.jsonl"
    assert collector.DEFAULT_OUTPUTS["1h"] == expected_root / "data/forward/global_market_candles_1h_v1.jsonl"
    assert collector.DEFAULT_OUTPUTS["4h"] == expected_root / "data/forward/global_market_candles_4h_v1.jsonl"
