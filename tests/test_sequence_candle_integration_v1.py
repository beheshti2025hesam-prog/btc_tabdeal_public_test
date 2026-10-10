import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

from forward import sequence_candle_integration_v1 as integration_module
from forward import source_evidence_registry_v1 as registry_module
from forward.sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1


ASOF = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def pinned_test_evidence_registry(tmp_path: Path, monkeypatch, request):
    artifact = tmp_path / "fixture-evidence.txt"
    artifact.write_text("synthetic reviewed test evidence\n", encoding="utf-8")
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
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    monkeypatch.setattr(registry_module, "PINNED_SOURCE_EVIDENCE_REGISTRY_SHA256",
                        hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(integration_module, "DEFAULT_SOURCE_EVIDENCE_REGISTRY_PATH", path)

    # Test-only harness: isolate downstream algorithm tests from the independent
    # provenance gate. Production modules are never given a bypass; dedicated
    # negative tests below keep the real verifier wired and fail-closed.
    if request.node.name in {
        "test_verified_contract_allows_unique_records_to_reach_closed_candle",
        "test_identical_repeated_sequence_blocks_candle_formation",
        "test_conflicting_reused_sequence_stops_candle_formation",
        "test_decreasing_sequence_is_not_assumed_to_be_out_of_order",
        "test_reconnect_requires_explicit_reset_before_new_sequence_epoch",
    }:
        monkeypatch.setattr(integration_module, "verify_source_evidence_bundle", lambda *args, **kwargs: object())


def rec(seq, ts="2026-10-07T06:30:00+00:00", price="100"):
    return {
        "source": "tabdeal_ws_forward_v1",
        "symbol": "BTC_USDT",
        "price": price,
        "amount": "1",
        "side": "buy",
        "source_updated": ts,
        "sequence": seq,
    }


def verified_ingestion():
    return SequenceAwareCandleIngestionV1(
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-exact-feed-completeness-evidence",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-exact-feed-ordering-evidence",
    )


def test_verified_contract_allows_unique_records_to_reach_closed_candle():
    s = verified_ingestion()
    result = s.ingest(
        [rec(1, "2026-10-07T06:30:00+00:00", "100"),
         rec(3, "2026-10-07T06:35:00+00:00", "105")],
        as_of=ASOF,
    )
    assert result.safe_for_decision is True
    assert len(result.candles) == 1
    assert [e.status for e in result.events] == ["ACCEPTED", "ACCEPTED"]


def test_unverified_contract_never_produces_decision_grade_candles():
    result = SequenceAwareCandleIngestionV1().ingest([rec(1)], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()


def test_identical_repeated_sequence_blocks_candle_formation():
    result = verified_ingestion().ingest([rec(1), dict(rec(1))], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.events[-1].reason == "REPEATED_SEQUENCE_IDENTITY_UNPROVEN"


def test_conflicting_reused_sequence_stops_candle_formation():
    result = verified_ingestion().ingest([rec(1), rec(1, price="101")], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.events[-1].reason == "SOURCE_SEQUENCE_REUSE_OBSERVED_ORDERING_SEMANTICS_UNKNOWN"


def test_decreasing_sequence_is_not_assumed_to_be_out_of_order():
    result = verified_ingestion().ingest([rec(12), rec(11)], as_of=ASOF)
    assert result.safe_for_decision is True
    assert [e.status for e in result.events] == ["ACCEPTED", "ACCEPTED"]


def test_reconnect_requires_explicit_reset_before_new_sequence_epoch():
    s = verified_ingestion()
    first = s.ingest([rec(10)], as_of=ASOF)
    assert first.safe_for_decision is True
    s.sequence.reset_for_reconnect()
    second = s.ingest([rec(10)], as_of=ASOF)
    assert second.safe_for_decision is True
    assert second.events[0].status == "ACCEPTED"


def test_unregistered_references_cannot_authorize_candle_ingestion():
    result = SequenceAwareCandleIngestionV1(
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="caller-made-up:contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="caller-made-up:completeness",
        source_ordering_verified=True,
        source_ordering_evidence_ref="caller-made-up:ordering",
    ).ingest([rec(1)], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.reason == "SOURCE_EVIDENCE_REF_NOT_REGISTERED"
