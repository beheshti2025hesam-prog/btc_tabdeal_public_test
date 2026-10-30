import hashlib
import json

import pytest

from forward.sequence_semantics_v1 import (
    SequenceCapabilitiesV1,
    SequenceIntegrityV2,
    SequenceSemanticsError,
    SequenceSemanticsRegistryV1,
)


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "forward" / "sequence_semantics_registry_v1.json"


def caps(**overrides):
    values = dict(
        record_id="test:ordered",
        semantic_class="ORDERED_EVENT_SEQUENCE",
        field_path="sequence",
        scope=("venue", "product", "channel", "symbol", "session_id"),
        ordered=True,
        event_identity=True,
        contiguous=False,
        gap_detection=False,
        snapshot_bootstrap=False,
        exact_payload_replay_only=True,
        registry_sha256="a" * 64,
        source_content_sha256="b" * 64,
        review_revision="synthetic-test-only",
        status="VERIFIED",
    )
    values.update(overrides)
    return SequenceCapabilitiesV1(**values)


def rec(sequence, *, price="100", session="s1", raw_hash=None):
    value = {
        "venue": "test",
        "product": "spot",
        "channel": "trade",
        "symbol": "BTCUSDT",
        "session_id": session,
        "sequence": sequence,
        "price": price,
    }
    if raw_hash is not None:
        value["raw_payload_sha256"] = raw_hash
    return value


def test_tabdeal_trade_sequence_is_explicitly_unknown_and_cannot_resolve():
    raw = REGISTRY_PATH.read_bytes()
    registry = SequenceSemanticsRegistryV1.load(
        REGISTRY_PATH, expected_sha256=hashlib.sha256(raw).hexdigest()
    )
    record = registry.inspect("tabdeal_fapi_broadcast_trade_sequence_v1")
    assert record["status"] == "UNKNOWN"
    assert record["semantic_class"] == "OPAQUE_METADATA"
    assert record["claims"]["ordered"] == "unknown"
    assert record["capabilities"]["event_identity"] is False
    assert record["capabilities"]["contiguous_gap_detection"] is False
    with pytest.raises(SequenceSemanticsError, match="SEQUENCE_SEMANTICS_NOT_VERIFIED"):
        registry.resolve(
            "tabdeal_fapi_broadcast_trade_sequence_v1",
            expected_key=record["key"],
        )


def test_registry_hash_is_pinned_and_tampering_is_rejected(tmp_path):
    path = tmp_path / "registry.json"
    path.write_bytes(REGISTRY_PATH.read_bytes() + b" ")
    with pytest.raises(SequenceSemanticsError, match="SEQUENCE_REGISTRY_HASH_MISMATCH"):
        SequenceSemanticsRegistryV1.load(
            path, expected_sha256=hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()
        )


def test_verified_record_requires_pinned_primary_source_hash():
    payload = {
        "schema": "hes_sequence_semantics_registry_v1",
        "records": [{
            "record_id": "bad",
            "key": {name: "x" for name in (
                "venue", "product", "endpoint", "channel", "message_type",
                "field_path", "protocol_version"
            )},
            "claims": {},
            "capabilities": {},
            "status": "VERIFIED",
            "source_evidence": {"source_kind": "primary", "source_content_sha256": None},
        }],
    }
    raw = json.dumps(payload).encode()
    with pytest.raises(SequenceSemanticsError, match="VERIFIED_RECORD_SOURCE_HASH_MISSING"):
        SequenceSemanticsRegistryV1.load(
            _write_temp_payload(raw), expected_sha256=hashlib.sha256(raw).hexdigest()
        )


def _write_temp_payload(raw):
    import tempfile
    from pathlib import Path
    handle = tempfile.NamedTemporaryFile(delete=False)
    handle.write(raw)
    handle.close()
    return Path(handle.name)


def test_unknown_semantics_block_before_reading_numeric_value():
    engine = SequenceIntegrityV2(None)
    result = engine.observe(rec(True))
    assert result.status == "BLOCKED"
    assert result.reason == "SEQUENCE_SEMANTICS_UNVERIFIED"


@pytest.mark.parametrize("value", [True, False, 1.0, "1", -1])
def test_sequence_wire_value_is_not_coerced(value):
    engine = SequenceIntegrityV2(caps())
    result = engine.observe(rec(value))
    assert result.status == "BLOCKED"
    assert result.reason == "SEQUENCE_VALUE_MUST_BE_NONNEGATIVE_INTEGER"


def test_non_contiguous_ordered_ids_do_not_imply_missing_events():
    engine = SequenceIntegrityV2(caps())
    assert engine.observe(rec(10)).status == "ACCEPTED"
    result = engine.observe(rec(12))
    assert result.status == "ACCEPTED"
    assert result.reason is None


def test_contiguous_contract_detects_gap_only_when_explicitly_capable():
    engine = SequenceIntegrityV2(caps(contiguous=True, gap_detection=True))
    assert engine.observe(rec(10)).status == "ACCEPTED"
    result = engine.observe(rec(12))
    assert result.status == "REJECT_STREAM"
    assert result.reason == "MISSING_EVENT"


def test_same_identity_exact_payload_replay_is_idempotent():
    engine = SequenceIntegrityV2(caps())
    raw_hash = "c" * 64
    assert engine.observe(rec(10, raw_hash=raw_hash)).status == "ACCEPTED"
    result = engine.observe(rec(10, raw_hash=raw_hash))
    assert result.status == "IDEMPOTENT_DUPLICATE"
    assert result.reason == "EXACT_RAW_PAYLOAD_REPLAY"


def test_conflicting_payload_for_documented_identity_blocks():
    engine = SequenceIntegrityV2(caps())
    assert engine.observe(rec(10, price="100")).status == "ACCEPTED"
    result = engine.observe(rec(10, price="101"))
    assert result.status == "REJECT_STREAM"
    assert result.reason == "CONFLICTING_DUPLICATE_IDENTITY"


def test_scope_change_blocks_cross_symbol_or_session_comparison():
    engine = SequenceIntegrityV2(caps())
    assert engine.observe(rec(10)).status == "ACCEPTED"
    result = engine.observe(rec(11, session="s2"))
    assert result.status == "BLOCKED"
    assert result.reason == "SEQUENCE_SCOPE_CHANGED"


def test_reconnect_reset_starts_new_epoch():
    engine = SequenceIntegrityV2(caps())
    assert engine.observe(rec(100)).status == "ACCEPTED"
    engine.reset_for_reconnect()
    assert engine.observe(rec(1, session="s2")).status == "ACCEPTED"
