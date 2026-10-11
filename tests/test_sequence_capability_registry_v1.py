import hashlib
import json

import pytest

from forward.sequence_capability_registry_v1 import (
    RegistryError,
    load_verified_contract,
)

SCOPE = {
    "venue": "tabdeal",
    "product": "fapi-futures-margin",
    "transport": "websocket",
    "endpoint": "wss://api1.tabdeal.org/special_margin/broadcast/",
    "channel_or_topic": "BTC_USDT raw-text subscription",
    "message_type": "trade-envelope",
    "field_path": "trade.sequence",
    "protocol_version": "unknown",
}


def write_registry(tmp_path, *, status="active-but-conservative", claims=None, evidence=None):
    claims = claims or {
        "unique": "unknown", "monotonic": "unknown", "contiguous": "unknown",
        "ordered": "unknown", "comparable_across_reconnect": "unknown",
        "comparable_across_symbols": "unknown", "comparable_across_channels": "unknown",
        "gap_detection_supported": False, "duplicate_identity_supported": False,
    }
    record = {
        **SCOPE,
        "semantic_class": "unknown",
        "status": status,
        "claims": claims,
        "source_evidence": evidence or [{
            "url": "https://docs.tabdeal.org/",
            "source_kind": "primary",
            "retrieved_at": "2026-10-10",
            "evidence_excerpt": "Broadcast envelope only; inner trade fields are not defined.",
        }],
    }
    registry = {
        "schema": "hes_sequence_capability_registry_v1",
        "registry_revision": "2026-10-10.1",
        "records": [record],
    }
    raw = (json.dumps(registry, sort_keys=True, separators=(",", ":")) + "\n").encode()
    registry_path = tmp_path / "registry.json"
    registry_path.write_bytes(raw)
    lock_path = tmp_path / "registry.lock.json"
    lock_path.write_text(json.dumps({
        "schema": "hes_sequence_registry_lock_v1",
        "registry_revision": "2026-10-10.1",
        "registry_sha256": hashlib.sha256(raw).hexdigest(),
    }), encoding="utf-8")
    return registry_path, lock_path


def test_tabdeal_unknown_sequence_does_not_authorize_gap_detection(tmp_path):
    registry, lock = write_registry(tmp_path)
    result = load_verified_contract(registry, lock, SCOPE)
    assert result.semantic_class == "unknown"
    assert result.gap_detection_authorized is False
    assert result.capabilities["contiguous"] == "unknown"


def test_modified_registry_bytes_fail_hash_lock(tmp_path):
    registry, lock = write_registry(tmp_path)
    registry.write_bytes(registry.read_bytes() + b" ")
    with pytest.raises(RegistryError, match="REGISTRY_DIGEST_MISMATCH"):
        load_verified_contract(registry, lock, SCOPE)


def test_wrong_channel_or_scope_is_rejected(tmp_path):
    registry, lock = write_registry(tmp_path)
    wrong_scope = {**SCOPE, "channel_or_topic": "other-channel"}
    with pytest.raises(RegistryError, match="SCOPE_NOT_UNIQUELY_REGISTERED"):
        load_verified_contract(registry, lock, wrong_scope)


def test_missing_scope_dimensions_are_rejected(tmp_path):
    registry, lock = write_registry(tmp_path)
    with pytest.raises(RegistryError, match="EXPECTED_SCOPE_INCOMPLETE"):
        load_verified_contract(registry, lock, {"venue": "tabdeal"})


def test_test_fixture_reference_cannot_prove_positive_capability(tmp_path):
    claims = {
        "unique": True, "monotonic": True, "contiguous": True, "ordered": True,
        "comparable_across_reconnect": False, "comparable_across_symbols": False,
        "comparable_across_channels": False, "gap_detection_supported": True,
        "duplicate_identity_supported": False,
    }
    registry, lock = write_registry(
        tmp_path, status="verified", claims=claims,
        evidence=[{
            "url": "test-fixture:authoritative-contract",
            "source_kind": "test",
            "retrieved_at": "today",
            "evidence_excerpt": "fixture",
        }],
    )
    with pytest.raises(RegistryError, match="NON_PRIMARY_EVIDENCE"):
        load_verified_contract(registry, lock, SCOPE)


def test_positive_capability_requires_hashed_source_snapshot(tmp_path):
    claims = {
        "unique": True, "monotonic": True, "contiguous": True, "ordered": True,
        "comparable_across_reconnect": False, "comparable_across_symbols": False,
        "comparable_across_channels": False, "gap_detection_supported": True,
        "duplicate_identity_supported": False,
    }
    registry, lock = write_registry(
        tmp_path, status="verified", claims=claims,
        evidence=[{
            "url": "https://docs.tabdeal.org/",
            "source_kind": "primary",
            "retrieved_at": "2026-10-10",
            "evidence_excerpt": "some excerpt",
        }],
    )
    with pytest.raises(RegistryError, match="SOURCE_SNAPSHOT_NOT_HASH_PINNED"):
        load_verified_contract(registry, lock, SCOPE)


def test_duplicate_json_keys_are_rejected(tmp_path):
    registry, lock = write_registry(tmp_path)
    registry.write_text('{"schema":"hes_sequence_capability_registry_v1","schema":"x"}', encoding="utf-8")
    lock.write_text(json.dumps({
        "schema": "hes_sequence_registry_lock_v1",
        "registry_revision": "2026-10-10.1",
        "registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    with pytest.raises(RegistryError, match="DUPLICATE_JSON_KEY"):
        load_verified_contract(registry, lock, SCOPE)



def test_integer_is_not_accepted_as_boolean_capability(tmp_path):
    claims = {
        "unique": 1, "monotonic": "unknown", "contiguous": "unknown",
        "ordered": "unknown", "comparable_across_reconnect": "unknown",
        "comparable_across_symbols": "unknown", "comparable_across_channels": "unknown",
        "gap_detection_supported": False, "duplicate_identity_supported": False,
    }
    registry, lock = write_registry(tmp_path, claims=claims)
    with pytest.raises(RegistryError, match="CAPABILITY_VALUE_INVALID"):
        load_verified_contract(registry, lock, SCOPE)


def test_checked_in_tabdeal_record_and_lock_are_consistent():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    registry = root / "forward" / "sequence_capability_registry_v1.json"
    lock = root / "forward" / "sequence_capability_registry_v1.lock.json"
    contract = load_verified_contract(registry, lock, SCOPE)
    assert contract.status == "active-but-conservative"
    assert contract.semantic_class == "unknown"
    assert contract.gap_detection_authorized is False
