import hashlib
import json

from forward.forward_tabdeal_collector_v1 import (
    ForwardTabdealCollectorV1,
    normalize_trade,
)


def payload(sequence="0007", price="100", updated="2026-11-16T16:00:00+00:00"):
    trade = {
        "symbol": "BTC_USDT",
        "price": price,
        "amount": "0.01",
        "side": "buy",
        "updated": updated,
    }
    if sequence is not ...:
        trade["sequence"] = sequence
    return {"type": "trade", "trade": trade}


def test_missing_sequence_is_allowed_and_full_raw_payload_is_preserved():
    source = payload(sequence=...)
    raw_message = json.dumps(source, separators=(",", ":"))
    record = normalize_trade(
        source,
        raw_message=raw_message,
        received_at="2026-11-16T16:01:00+00:00",
    )
    assert record["sequence"] is None
    assert record["received_at"] == "2026-11-16T16:01:00+00:00"
    assert record["event_timestamp"] == "2026-11-16T16:00:00+00:00"
    assert record["market"] == "BTC_USDT"
    assert record["raw_payload"] == source
    assert record["raw_payload_json"] == raw_message
    assert record["raw_payload_sha256"] == hashlib.sha256(raw_message.encode()).hexdigest()


def test_repeated_sequence_values_are_appended_as_separate_receipts(tmp_path):
    collector = ForwardTabdealCollectorV1(str(tmp_path / "receipts.jsonl"), enabled=True)
    first = normalize_trade(payload(sequence=7, price="100"))
    second = normalize_trade(payload(sequence=7, price="101", updated="2026-11-16T16:00:01+00:00"))
    collector._append(first)
    collector._append(second)
    rows = [json.loads(line) for line in (tmp_path / "receipts.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert [row["sequence"] for row in rows] == [7, 7]
    assert [row["price"] for row in rows] == [100.0, 101.0]
    assert rows[0]["raw_payload"]["trade"]["price"] == "100"
    assert rows[1]["raw_payload"]["trade"]["price"] == "101"


def test_incomplete_trade_shape_is_still_captured_for_schema_drift():
    source = {"type": "trade", "trade": {"symbol": "BTC_USDT", "sequence": None}}
    record = normalize_trade(source)
    assert record is not None
    assert record["price"] is None
    assert record["amount"] is None
    assert record["event_timestamp"] is None
    assert record["raw_payload"] == source


def test_order_events_are_not_misclassified_as_trades():
    assert normalize_trade({"type": "order", "data": {"symbol": "BTC_USDT"}}) is None


def test_collector_remains_disabled_by_default():
    collector = ForwardTabdealCollectorV1()
    try:
        collector.run(run_seconds=1)
    except RuntimeError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("collector must remain disabled by default")
