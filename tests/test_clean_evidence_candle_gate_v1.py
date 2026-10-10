import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from forward import clean_evidence_candle_gate_v1 as gate_module
from forward import source_evidence_registry_v1 as registry_module
from forward.clean_evidence_candle_gate_v1 import CleanEvidenceCandleGateV1


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


def rec(seq, ts, price="100"):
    return {
        "source": "tabdeal_ws_forward_v1",
        "symbol": "BTC_USDT",
        "price": price,
        "amount": "1",
        "side": "buy",
        "source_updated": ts.isoformat(),
        "sequence": seq,
    }


def verified_gate():
    return CleanEvidenceCandleGateV1(
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-exact-feed-completeness-evidence",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-exact-feed-ordering-evidence",
    )


def test_empty_forward_input_blocks():
    r = CleanEvidenceCandleGateV1().evaluate([], as_of=datetime.now(timezone.utc))
    assert not r.safe and r.reason == "NO_FORWARD_RECORDS"


def test_default_gate_blocks_until_exact_feed_contract_is_verified():
    now = datetime.now(timezone.utc)
    r = CleanEvidenceCandleGateV1().evaluate(
        [rec(1, now - timedelta(minutes=20))], as_of=now
    )
    assert not r.safe
    assert r.reason == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED"
    assert r.candles == ()


def test_future_input_fails_closed_when_contract_gate_is_explicitly_satisfied():
    now = datetime.now(timezone.utc)
    r = verified_gate().evaluate([rec(1, now + timedelta(seconds=1))], as_of=now)
    assert not r.safe and r.reason == "INVALID_FORWARD_INPUT"


def test_conflicting_sequence_reuse_blocks_candle_evidence():
    now = datetime.now(timezone.utc)
    timestamp = now - timedelta(minutes=20)
    data = [rec(10, timestamp, "100"), rec(10, timestamp, "101")]
    r = verified_gate().evaluate(data, as_of=now)
    assert not r.safe
    assert r.reason == "SOURCE_SEQUENCE_REUSE_OBSERVED_ORDERING_SEMANTICS_UNKNOWN"
    assert r.candles == ()


def test_unverified_sequence_jump_does_not_infer_a_missing_trade():
    now = datetime.now(timezone.utc)
    data = [
        rec(10, now - timedelta(minutes=20)),
        rec(12, now - timedelta(minutes=1)),
    ]
    r = CleanEvidenceCandleGateV1(
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-exact-feed-completeness-evidence",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-exact-feed-ordering-evidence",
    ).evaluate(data, as_of=now)
    assert r.safe
    assert r.reason == "CANDLE_SAFE"
