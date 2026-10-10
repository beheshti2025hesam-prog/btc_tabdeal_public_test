import hashlib
import json
from pathlib import Path
import pytest

from forward import clean_evidence_sequence_gate_v1 as gate_module
from forward import source_evidence_registry_v1 as registry_module
from forward.clean_evidence_sequence_gate_v1 import CleanEvidenceSequenceGateV1


@pytest.fixture(autouse=True)
def pinned_test_evidence_registry(tmp_path: Path, monkeypatch):
    artifact = tmp_path / "fixture-evidence.txt"
    artifact.write_text("synthetic reviewed test evidence\\n", encoding="utf-8")
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    rows = [
        ("test-fixture:authoritative-contract", "sequence_contract"),
        ("test-fixture:reviewed-exact-feed-completeness-evidence", "source_completeness"),
        ("test-fixture:reviewed-exact-feed-ordering-evidence", "source_ordering"),
    ]
    entries = [
        {"evidence_ref": ref, "evidence_type": kind,
         "source_scope": "tabdeal-futures:BTC_USDT", "evidence_path": artifact.name,
         "evidence_sha256": artifact_sha, "review_status": "INDEPENDENTLY_REVIEWED",
         "review_record_ref": "test-fixture:independent-review"}
        for ref, kind in rows
    ]
    payload = {"schema": "hes_source_evidence_registry_v1", "status": "REVIEWED_PINNED",
               "registry_version": 1, "entries": entries}
    path = tmp_path / "source_evidence_registry_v1.json"
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\\n").encode()
    path.write_bytes(raw)
    monkeypatch.setattr(registry_module, "PINNED_SOURCE_EVIDENCE_REGISTRY_SHA256",
                        hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(gate_module, "DEFAULT_SOURCE_EVIDENCE_REGISTRY_PATH", path)


def rec(seq, price="1"):
    return {"sequence": seq, "price": price, "amount": "1", "symbol": "BTC_USDT"}


def verified_gate():
    return CleanEvidenceSequenceGateV1(
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-exact-feed-completeness-evidence",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-exact-feed-ordering-evidence",
    )


def test_default_gate_blocks_when_source_contract_is_unverified():
    r = CleanEvidenceSequenceGateV1().evaluate([rec(10), rec(11), rec(12)])
    assert not r.safe
    assert r.reason == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED"
    assert r.accepted == ()
    assert r.rejected == (rec(10), rec(11), rec(12))


def test_verified_contract_accepts_unique_native_sequences_without_gap_assumptions():
    r = verified_gate().evaluate([rec(10), rec(12), rec(11)])
    assert r.safe and len(r.accepted) == 3
    assert r.reason == "SOURCE_CONTRACT_GATES_VERIFIED"


def test_identical_repeated_sequence_is_not_idempotently_deduplicated():
    x = rec(10)
    r = verified_gate().evaluate([x, x, rec(11)])
    assert not r.safe
    assert r.reason == "REPEATED_SEQUENCE_IDENTITY_UNPROVEN"
    assert r.accepted == ()


def test_numeric_jump_does_not_itself_prove_loss():
    r = verified_gate().evaluate([rec(10), rec(12)])
    assert r.safe
    assert len(r.accepted) == 2


def test_decreasing_sequence_does_not_itself_prove_out_of_order():
    r = verified_gate().evaluate([rec(12), rec(10), rec(11)])
    assert r.safe
    assert len(r.accepted) == 3


def test_same_sequence_different_payload_blocks_evidence():
    r = verified_gate().evaluate([rec(10, "1"), rec(10, "2")])
    assert not r.safe
    assert r.reason == "SOURCE_SEQUENCE_REUSE_OBSERVED_ORDERING_SEMANTICS_UNKNOWN"


def test_native_string_sequence_is_preserved_not_integer_parsed():
    r = verified_gate().evaluate([rec("not-a-number")])
    assert r.safe
    assert r.accepted == (rec("not-a-number"),)


def test_unsupported_sequence_type_blocks_evidence():
    r = verified_gate().evaluate([rec([])])
    assert not r.safe
    assert r.reason == "INVALID_SEQUENCE_TYPE"
