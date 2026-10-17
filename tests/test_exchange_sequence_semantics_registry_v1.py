import json
from pathlib import Path


REGISTRY_PATH = Path("forward/exchange_sequence_semantics_registry_v1.json")
ALLOWED_CAPABILITIES = {"UNKNOWN", "DOCUMENTED", "UNSUPPORTED"}
ALLOWED_DECISION_CAPABILITIES = {
    "OBSERVATION_ONLY",
    "ADAPTER_SPECIFIC_BOOK_SYNC_ONLY",
}


def load_registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_registry_has_explicit_fail_closed_defaults():
    registry = load_registry()
    assert registry["schema"] == "hes_exchange_sequence_semantics_registry_v1"
    assert registry["status"] == "RESEARCH_ONLY"
    policy = registry["policy"]
    assert policy["default_capability"] == "UNKNOWN"
    assert policy["unknown_semantics_may_drive_gap_detection"] is False
    assert policy["unknown_semantics_may_drive_conflict_rejection"] is False
    assert policy["cross_reconnect_comparison_default"] is False
    assert policy["timestamps_are_sequence_evidence"] is False
    assert policy["fail_closed_for_decision_use"] is True


def test_registry_ids_are_unique_and_evidence_is_pinned():
    records = load_registry()["records"]
    ids = [record["id"] for record in records]
    assert ids and len(ids) == len(set(ids))
    for record in records:
        assert record["venue"] and record["product"] and record["endpoint"]
        assert record["channel"] and record["message_type"]
        assert record["evidence"]["source_url"].startswith("https://")
        assert record["evidence"]["retrieved_on"]
        assert record["evidence"]["claim"]
        assert record["decision_capability"] in ALLOWED_DECISION_CAPABILITIES
        for capability in record["capabilities"].values():
            assert capability in ALLOWED_CAPABILITIES


def test_tabdeal_trade_sequence_is_not_promoted_to_identity_or_gap_detector():
    registry = load_registry()
    record = next(
        item for item in registry["records"]
        if item["id"] == "tabdeal.fapi.special_margin.broadcast.trade.v1"
    )
    assert record["field_path"] == "trade.sequence"
    assert record["capabilities"]["event_identity"] == "UNKNOWN"
    assert record["capabilities"]["ordered"] == "UNKNOWN"
    assert record["capabilities"]["contiguous"] == "UNKNOWN"
    assert record["capabilities"]["gap_detection"] == "UNSUPPORTED"
    assert record["capabilities"]["cross_reconnect_comparable"] == "UNSUPPORTED"
    assert record["decision_capability"] == "OBSERVATION_ONLY"


def test_tabdeal_rest_sequence_is_not_a_websocket_bridge():
    registry = load_registry()
    record = next(
        item for item in registry["records"]
        if item["id"] == "tabdeal.fapi.aggDepth.rest.sequence.v1"
    )
    assert record["capabilities"]["snapshot_delta_bridge"] == "UNSUPPORTED"
    assert record["decision_capability"] == "OBSERVATION_ONLY"


def test_documented_binance_spot_depth_capability_is_channel_scoped():
    registry = load_registry()
    record = next(
        item for item in registry["records"]
        if item["id"] == "binance.spot.depth.diff.v1"
    )
    assert record["capabilities"]["ordered"] == "DOCUMENTED"
    assert record["capabilities"]["contiguous"] == "DOCUMENTED"
    assert record["capabilities"]["gap_detection"] == "DOCUMENTED"
    assert record["capabilities"]["snapshot_delta_bridge"] == "DOCUMENTED"
    assert record["capabilities"]["cross_reconnect_comparable"] == "UNSUPPORTED"
    assert record["decision_capability"] == "ADAPTER_SPECIFIC_BOOK_SYNC_ONLY"
