"""Regression vectors for exact-scope, fail-closed exchange sequence semantics."""
import pytest

from forward.sequence_semantics_registry_v1 import load_default_registry


def tabdeal_broadcast(registry):
    return registry.resolve(
        venue="tabdeal",
        product="fapi_futures_margin",
        endpoint="wss://api1.tabdeal.org/special_margin/broadcast/",
        channel="BTC_USDT_raw_text_subscription",
        message_type="trade_envelope",
        field_path="trade.sequence",
        protocol_version="unknown",
    )


@pytest.mark.parametrize(
    "scope_field",
    ["venue", "product", "endpoint", "channel", "message_type", "field_path", "protocol_version"],
)
def test_registry_resolution_never_crosses_any_contract_scope_dimension(scope_field):
    values = {
        "venue": "tabdeal",
        "product": "fapi_futures_margin",
        "endpoint": "wss://api1.tabdeal.org/special_margin/broadcast/",
        "channel": "BTC_USDT_raw_text_subscription",
        "message_type": "trade_envelope",
        "field_path": "trade.sequence",
        "protocol_version": "unknown",
    }
    registry = load_default_registry()
    assert tabdeal_broadcast(registry) is not None
    values[scope_field] += "_different"
    assert registry.resolve(**values) is None


def test_unknown_sequence_contract_never_infers_gap_for_generated_numeric_progress():
    registry = load_default_registry()
    contract = tabdeal_broadcast(registry)
    for previous in range(256):
        for delta in range(1, 17):
            assert registry.classify_numeric_gap(
                contract, previous=previous, current=previous + delta
            ) == "NOT_INFERABLE_FROM_NUMERIC_GAP"


@pytest.mark.parametrize(
    "previous,current",
    [(True, 2), (1, False), (1.0, 3), ("1", 3), (1, "3")],
)
def test_numeric_gap_rejects_boolean_and_coerced_numeric_inputs(previous, current):
    registry = load_default_registry()
    contract = tabdeal_broadcast(registry)
    assert registry.classify_numeric_gap(
        contract, previous=previous, current=current
    ) == "INVALID_NUMERIC_INPUT"


def test_tabdeal_official_reply_body_is_hash_pinned_but_capabilities_stay_unknown():
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    body_path = root / "docs/protocol/evidence/tabdeal_broadcast_reply_2026-11-04.fa.txt"
    meta_path = root / "docs/protocol/evidence/tabdeal_broadcast_reply_2026-11-04.metadata.json"
    body = body_path.read_bytes()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert hashlib.sha256(body).hexdigest() == meta["body_sha256"]
    assert meta["source_headers_available"] is False

    registry = load_default_registry()
    contract = tabdeal_broadcast(registry)
    assert contract is not None
    evidence = contract["evidence"]
    pinned = [row for row in evidence if row.get("evidence_ref") == "tabdeal-official-reply-body:2026-11-04"]
    assert len(pinned) == 1
    assert pinned[0]["source_snapshot_sha256"] == meta["body_sha256"]
    assert pinned[0]["excerpt_sha256"] == meta["body_sha256"]
    for capability in ("event_identity_unique", "ordered_within_scope", "contiguous_within_scope", "gap_detectable", "cross_reconnect_comparable"):
        assert registry.capability(contract, capability) == "unknown"
