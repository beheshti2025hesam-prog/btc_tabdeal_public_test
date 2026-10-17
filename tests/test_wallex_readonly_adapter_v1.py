from datetime import datetime, timezone
import hashlib
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
