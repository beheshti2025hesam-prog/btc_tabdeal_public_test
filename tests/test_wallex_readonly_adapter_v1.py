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


class FakeWebSocket:
    def __init__(self, frames=(), *, error=None):
        self.frames = list(frames)
        self.error = error
        self.events = []
        self.sent = []
        self.closed = False

    def send(self, payload):
        self.events.append("send")
        self.sent.append(payload)

    def settimeout(self, _value):
        pass

    def recv(self):
        self.events.append("recv")
        if self.error is not None:
            raise self.error
        if self.frames:
            return self.frames.pop(0)
        raise TimeoutError("mock timeout")

    def close(self):
        self.closed = True


def frame(value):
    return json.dumps(value, separators=(",", ":"))


def test_run_once_subscribes_immediately_then_persists_trade(tmp_path):
    fake = FakeWebSocket([
        frame({"sid": "session-1", "pingInterval": 20000}),
        frame(["USDTTMN@trade", valid()]),
    ])
    output = tmp_path / "events.jsonl"
    collector = WallexReadOnlyCollectorV1(
        output=str(output), symbol="USDTTMN", enabled=True,
        max_runtime_seconds=0.02, ws_factory=lambda: fake,
    )
    collector.run_once()
    assert fake.events[0] == "send"
    assert fake.events[1] == "recv"
    assert json.loads(fake.sent[0]) == ["subscribe", {"channel": "USDTTMN@trade"}]
    assert collector.frames_seen == 2
    assert collector.records_written == 1
    assert collector.ignored == 1
    saved = json.loads(output.read_text().splitlines()[0])
    assert saved["symbol"] == "USDTTMN"
    assert saved["sequence"] is None
    assert fake.closed


def test_repeated_run_once_appends_durable_records_after_restart(tmp_path):
    output = tmp_path / "events.jsonl"
    fakes = [
        FakeWebSocket([frame(["BTCUSDT@trade", valid()])]),
        FakeWebSocket([frame(["BTCUSDT@trade", valid()])]),
    ]
    collector = WallexReadOnlyCollectorV1(
        output=str(output), enabled=True, max_runtime_seconds=0.02,
        ws_factory=lambda: fakes.pop(0),
    )
    collector.run_once()
    collector.run_once()
    lines = output.read_text().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["sequence"] is None for line in lines)


def test_silent_second_session_fails_even_after_previous_session_wrote_data(tmp_path):
    output = tmp_path / "events.jsonl"
    fakes = [
        FakeWebSocket([frame(["BTCUSDT@trade", valid()])]),
        FakeWebSocket([frame({"sid": "session-silent"})]),
    ]
    collector = WallexReadOnlyCollectorV1(
        output=str(output), enabled=True, max_runtime_seconds=0.02,
        ws_factory=lambda: fakes.pop(0),
    )
    collector.run_once()
    assert collector.records_written == 1
    with pytest.raises(RuntimeError, match="no valid trade events"):
        collector.run_once()
    assert collector.records_written == 1
    assert len(output.read_text().splitlines()) == 1
    assert collector.last_error == "no_trade_events_received"


def test_subscription_send_failure_fails_closed(tmp_path):
    class SendFailure(FakeWebSocket):
        def send(self, payload):
            raise OSError("subscribe send failed")

    fake = SendFailure()
    collector = WallexReadOnlyCollectorV1(
        output=str(tmp_path / "events.jsonl"), enabled=True,
        max_runtime_seconds=0.02, ws_factory=lambda: fake,
    )
    with pytest.raises(RuntimeError, match="subscription failed"):
        collector.run_once()
    assert collector.last_error == "OSError"
    assert fake.closed


def test_silent_feed_fails_closed_even_if_connection_opens(tmp_path):
    fake = FakeWebSocket([frame({"sid": "session-silent"})])
    collector = WallexReadOnlyCollectorV1(
        output=str(tmp_path / "events.jsonl"), enabled=True,
        max_runtime_seconds=0.02, ws_factory=lambda: fake,
    )
    with pytest.raises(RuntimeError, match="no valid trade events"):
        collector.run_once()
    assert collector.last_error == "no_trade_events_received"
    assert collector.records_written == 0
    assert not (tmp_path / "events.jsonl").exists()
    assert fake.closed


def test_unexpected_disconnect_fails_closed(tmp_path):
    fake = FakeWebSocket(error=OSError("network down"))
    collector = WallexReadOnlyCollectorV1(
        output=str(tmp_path / "events.jsonl"), enabled=True,
        max_runtime_seconds=0.02, ws_factory=lambda: fake,
    )
    with pytest.raises(RuntimeError, match="disconnected"):
        collector.run_once()
    assert collector.last_error == "OSError"
    assert collector.records_written == 0
    assert not (tmp_path / "events.jsonl").exists()
    assert fake.closed


def test_malformed_frame_and_wrong_channel_are_not_written(tmp_path):
    fake = FakeWebSocket([
        "{not-json",
        frame(["OTHER@trade", valid()]),
        frame(["BTCUSDT@trade", {"price": "NaN"}]),
    ])
    collector = WallexReadOnlyCollectorV1(
        output=str(tmp_path / "events.jsonl"), enabled=True,
        max_runtime_seconds=0.02, ws_factory=lambda: fake,
    )
    with pytest.raises(RuntimeError, match="no valid trade events"):
        collector.run_once()
    assert collector.records_written == 0
    assert collector.rejected >= 2
    assert collector.ignored >= 1
