import hashlib
import json

import pytest

from forward.forward_tabdeal_collector_v1 import (
    ForwardTabdealCollectorV1,
    SEQUENCE_SEMANTICS,
    normalize_trade,
)


def frame(sequence_marker=True, sequence=10, price="100"):
    trade = {
        "symbol": "BTC_USDT", "price": price, "amount": "0.01",
        "side": "buy", "updated": "2026-11-04T13:41:26Z",
    }
    if sequence_marker:
        trade["sequence"] = sequence
    return {"trade": trade}


def test_sequence_is_preserved_as_informational_only_metadata():
    r = normalize_trade(frame(sequence=900))
    assert r["sequence_raw"] == 900
    assert r["sequence_semantics"] == SEQUENCE_SEMANTICS
    assert r["sequence_scope"].startswith("UNSPECIFIED_NO_GLOBAL")
    assert r["depth_sequence_policy"].startswith("INDEPENDENT_SEPARATE_FIELD")
    assert r["decision_grade"] is False
    assert r["recovery_status"].startswith("RECONNECT_RESUBSCRIBE_ONLY")
    assert r["snapshot_reconciliation_status"] == "NOT_IMPLEMENTED"


def test_missing_sequence_does_not_reject_trade_shape():
    r = normalize_trade(frame(sequence_marker=False))
    assert r is not None
    assert r["sequence_raw"] is None


def test_repeated_sequence_with_different_payloads_are_not_conflicts_here():
    a = normalize_trade(frame(sequence=77, price="100"))
    b = normalize_trade(frame(sequence=77, price="101"))
    assert a is not None and b is not None
    assert a["sequence_raw"] == b["sequence_raw"]
    assert a["raw_payload_sha256"] != b["raw_payload_sha256"]


def test_regressing_sequence_is_not_rejected_by_normalizer():
    a = normalize_trade(frame(sequence=100))
    b = normalize_trade(frame(sequence=4))
    assert a is not None and b is not None
    assert (a["sequence_raw"], b["sequence_raw"]) == (100, 4)


def test_boolean_sequence_is_not_coerced_to_integer():
    r = normalize_trade(frame(sequence=True))
    assert r["sequence_raw"] is None


def test_exact_wire_payload_market_receive_and_event_timestamps_are_persisted():
    raw = '{ "trade": {"symbol":"BTC_USDT","price":"100.00","amount":"0.0100","side":"buy","updated":"2026-11-04T13:41:26Z","sequence":77} }'
    received = "2026-11-04T13:41:27.123456+00:00"
    r = normalize_trade(json.loads(raw), raw_message=raw, received_at=received)
    assert r is not None
    assert r["raw_payload"] == raw
    assert r["raw_payload_encoding"] == "utf-8"
    assert r["raw_payload_sha256"] == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert r["market"] == "BTC_USDT"
    assert r["received_at"] == received
    assert r["event_timestamp"] == "2026-11-04T13:41:26Z"
    assert r["source_updated"] == "2026-11-04T13:41:26Z"
    assert r["price_raw"] == "100.00"
    assert r["amount_raw"] == "0.0100"


def test_incomplete_trade_envelope_is_preserved_and_quarantined():
    payload = {"trade": {"symbol": "BTC_USDT", "price": "bad", "sequence": 8}}
    raw = json.dumps(payload)
    r = normalize_trade(payload, raw_message=raw, received_at="2026-11-04T13:41:27Z")
    assert r is not None
    assert r["raw_payload"] == raw
    assert r["normalization_status"] == "INCOMPLETE_RAW_PRESERVED"
    assert "PRICE_INVALID" in r["reason_codes"]
    assert "AMOUNT_MISSING" in r["reason_codes"]
    assert "EVENT_TIMESTAMP_MISSING" in r["reason_codes"]
    assert r["decision_grade"] is False


def test_non_target_market_is_preserved_but_marked_as_mismatch():
    payload = {"trade": {"symbol": "ETH_USDT", "price": "100", "amount": "1", "updated": "2026-11-04T13:41:26Z"}}
    r = normalize_trade(payload)
    assert r is not None
    assert r["market"] == "ETH_USDT"
    assert r["normalization_status"] == "INCOMPLETE_RAW_PRESERVED"
    assert "MARKET_MISMATCH" in r["reason_codes"]


def test_collector_is_disabled_by_default():
    collector = ForwardTabdealCollectorV1()
    assert collector.enabled is False
    with pytest.raises(RuntimeError, match="disabled by default"):
        collector.run(run_seconds=1)


def test_byte_payload_uses_exact_wire_hash():
    raw = b'{"trade":{"symbol":"BTC_USDT","price":"100","amount":"0.01","updated":"2026-11-04T13:41:26Z"}}'
    r = normalize_trade(json.loads(raw), raw_message=raw)
    assert r is not None
    assert r["raw_payload_sha256"] == hashlib.sha256(raw).hexdigest()
    assert r["raw_payload_encoding"] == "utf-8"