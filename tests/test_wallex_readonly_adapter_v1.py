from datetime import datetime, timezone
import json

import pytest

from forward.wallex_readonly_adapter_v1 import WallexReadOnlyCollectorV1, normalize_trade


AS_OF = datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc)


def valid():
    return {
        "price": "62000.1250",
        "quantity": "0.001200",
        "isBuyOrder": True,
        "timestamp": "2026-10-17T09:59:59Z",
    }


def test_normalizes_documented_wallex_trade_without_inventing_sequence():
    result = normalize_trade("BTCUSDT@trade", valid(), received_at=AS_OF)
    assert result["venue"] == "wallex"
    assert result["product"] == "spot"
    assert result["symbol"] == "BTCUSDT"
    assert result["price"] == "62000.1250"
    assert result["amount"] == "0.001200"
    assert result["side"] == "BUY"
    assert result["sequence"] is None
    assert result["sequence_semantics"] == "NOT_DOCUMENTED_BY_VENUE"
    assert result["source_updated"] == "2026-10-17T09:59:59+00:00"
    assert len(result["raw_payload_sha256"]) == 64


def test_normalizes_configured_non_default_symbol():
    result = normalize_trade("USDTTMN@trade", valid(), symbol="USDTTMN", received_at=AS_OF)
    assert result["symbol"] == "USDTTMN"


def test_sell_side_is_normalized():
    payload = valid()
    payload["isBuyOrder"] = False
    assert normalize_trade("BTCUSDT@trade", payload, received_at=AS_OF)["side"] == "SELL"


@pytest.mark.parametrize("channel", ["BTC_USDT@trade", "ETHUSDT@trade", "BTCUSDT@depth"])
def test_rejects_wrong_channel(channel):
    with pytest.raises(ValueError):
        normalize_trade(channel, valid(), received_at=AS_OF)


@pytest.mark.parametrize("field,value", [
    ("price", "0"), ("price", "-1"), ("price", "NaN"),
    ("quantity", "0"), ("quantity", "-0.1"), ("quantity", "Infinity"),
    ("isBuyOrder", 1), ("timestamp", "2026-10-17T09:00:00"),
])
def test_rejects_invalid_required_values(field, value):
    payload = valid()
    payload[field] = value
    with pytest.raises(ValueError):
        normalize_trade("BTCUSDT@trade", payload, received_at=AS_OF)


def test_same_payload_has_stable_hash_and_different_payload_changes_hash():
    one = normalize_trade("BTCUSDT@trade", valid(), received_at=AS_OF)
    two = normalize_trade("BTCUSDT@trade", valid(), received_at=AS_OF)
    changed = valid()
    changed["price"] = "62001"
    three = normalize_trade("BTCUSDT@trade", changed, received_at=AS_OF)
    assert one["raw_payload_sha256"] == two["raw_payload_sha256"]
    assert one["raw_payload_sha256"] != three["raw_payload_sha256"]


def test_collector_is_disabled_by_default(tmp_path):
    collector = WallexReadOnlyCollectorV1(output=str(tmp_path / "events.jsonl"))
    with pytest.raises(RuntimeError, match="disabled"):
        collector.run_once()


def test_collector_handles_and_persists_broadcaster_event(tmp_path):
    output = tmp_path / "events.jsonl"
    collector = WallexReadOnlyCollectorV1(output=str(output), symbol="USDTTMN", enabled=True)
    collector._handle_event("USDTTMN@trade", valid())
    collector._handle_event("OTHER@trade", valid())
    lines = output.read_text().splitlines()
    assert collector.frames_seen == 2
    assert collector.records_written == 1
    assert collector.ignored == 1
    assert len(lines) == 1
    saved = json.loads(lines[0])
    assert saved["symbol"] == "USDTTMN"
    assert saved["sequence"] is None


def test_run_once_uses_socketio_subscribe_and_broadcaster(tmp_path):
    class FakeSocketIO:
        def __init__(self):
            self.handlers = {}
            self.connected = False
            self.emitted = []

        def on(self, event):
            def register(callback):
                self.handlers[event] = callback
                return callback
            return register

        def connect(self, url, transports):
            assert url == "https://api.wallex.ir"
            assert transports == ["websocket"]
            self.connected = True
            self.handlers["connect"]()

        def emit(self, event, payload):
            self.emitted.append((event, payload))
            self.handlers["Broadcaster"]("USDTTMN@trade", valid())

        def disconnect(self):
            self.connected = False

    fake = FakeSocketIO()
    output = tmp_path / "events.jsonl"
    collector = WallexReadOnlyCollectorV1(
        output=str(output), symbol="USDTTMN", enabled=True,
        max_runtime_seconds=0.01, sio_factory=lambda: fake,
    )
    collector.run_once()
    assert fake.emitted == [("subscribe", {"channel": "USDTTMN@trade"})]
    assert collector.records_written == 1
    assert json.loads(output.read_text())["sequence"] is None
