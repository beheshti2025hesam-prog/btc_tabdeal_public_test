from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import pytest

from forward import controlled_forward_observation_runner_v1 as runner_module
from forward import source_evidence_registry_v1 as registry_module

from forward.controlled_forward_observation_runner_v1 import (
    ControlledForwardObservationRunnerV1,
)


@pytest.fixture(autouse=True)
def pinned_test_evidence_registry(tmp_path: Path, monkeypatch):
    artifact = tmp_path / "fixture-evidence.txt"
    artifact.write_text("synthetic reviewed test evidence\\n", encoding="utf-8")
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    rows = [
        ("test-fixture:authoritative-contract", "sequence_contract"),
        ("test-fixture:reviewed-source-completeness", "source_completeness"),
        ("test-fixture:reviewed-source-ordering", "source_ordering"),
    ]
    entries = [
        {
            "evidence_ref": ref,
            "evidence_type": kind,
            "source_scope": "tabdeal-futures:BTC_USDT",
            "evidence_path": artifact.name,
            "evidence_sha256": artifact_sha,
            "review_status": "INDEPENDENTLY_REVIEWED",
            "review_record_ref": "test-fixture:independent-review",
        }
        for ref, kind in rows
    ]
    payload = {
        "schema": "hes_source_evidence_registry_v1",
        "status": "REVIEWED_PINNED",
        "registry_version": 1,
        "entries": entries,
    }
    path = tmp_path / "source_evidence_registry_v1.json"
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\\n").encode()
    path.write_bytes(raw)
    monkeypatch.setattr(
        registry_module, "PINNED_SOURCE_EVIDENCE_REGISTRY_SHA256",
        hashlib.sha256(raw).hexdigest(),
    )
    monkeypatch.setattr(runner_module, "DEFAULT_SOURCE_EVIDENCE_REGISTRY_PATH", path)


class FakeWS:
    def __init__(self, url, on_open, on_message):
        self.url = url
        self.on_open = on_open
        self.on_message = on_message

    def run_forever(self, **kwargs):
        self.on_open(self)
        for seq, price in ((100, "100.0"), (101, "101.0"), (102, "102.0")):
            updated = datetime.now(timezone.utc).isoformat()
            self.on_message(self, '{"trade": {"symbol":"BTC_USDT","price":"%s","amount":"0.1","side":"buy","sequence":%d,"updated":"%s"}}' % (price, seq, updated))

    def send(self, symbol):
        assert symbol == "BTC_USDT"

    def close(self):
        pass


def test_runner_uses_transport_and_writes_observation(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-source-completeness",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-source-ordering",
    )
    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )
    assert result.status == "WAITING"
    assert result.reason == "INSUFFICIENT_CLOSED_CANDLES"
    assert session.exists()
    assert not journal.exists()


def test_runner_accepts_non_contiguous_monotonic_sequence(tmp_path: Path):
    class GapTransport:
        def __init__(self, on_record, **kwargs):
            self.on_record = on_record

        def run_once(self):
            for seq in (100, 102):
                self.on_record({"symbol":"BTC_USDT","price":"100","amount":"0.1","side":"buy",
                                "sequence":seq,"timestamp":"2026-10-07T13:00:00Z"})

    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "journal.jsonl",
        session_path=tmp_path / "session.jsonl",
        transport_factory=GapTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-source-completeness",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-source-ordering",
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "WAITING"
    assert result.reason == "INSUFFICIENT_CLOSED_CANDLES"
    assert not (tmp_path / "journal.jsonl").exists()


def test_runner_does_not_write_when_transport_has_no_records(tmp_path: Path):
    class EmptyWS(FakeWS):
        def run_forever(self, **kwargs):
            self.on_open(self)

    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        ws_factory=EmptyWS,
        max_runtime_seconds=1,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-source-completeness",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-source-ordering",
    )
    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )
    assert result.status == "WAITING"
    assert result.reason == "NO_FRESH_RECORDS"
    assert not journal.exists()


def test_runner_fails_closed_on_transport_error(tmp_path: Path):
    class BrokenTransport:
        def __init__(self, **kwargs):
            pass

        def run_once(self):
            raise RuntimeError("simulated transport failure")

    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        transport_factory=BrokenTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-source-completeness",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-source-ordering",
    )
    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )
    assert result.status == "BLOCKED"
    assert result.reason == "TRANSPORT_ERROR:RuntimeError"
    assert result.records_received == 0
    assert session.exists()
    assert not journal.exists()


def test_runner_fails_closed_on_transport_construction_error(tmp_path: Path):
    class BrokenTransport:
        def __init__(self, **kwargs):
            raise RuntimeError("simulated construction failure")

    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        transport_factory=BrokenTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-source-completeness",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-source-ordering",
    )
    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )
    assert result.status == "BLOCKED"
    assert result.reason == "TRANSPORT_ERROR:RuntimeError"
    assert result.records_received == 0
    assert session.exists()
    assert not journal.exists()


def test_runner_fails_closed_when_record_bound_is_exceeded(tmp_path: Path):
    class OverLimitTransport:
        def __init__(self, on_record, **kwargs):
            self.on_record = on_record

        def run_once(self):
            for seq in range(4):
                self.on_record({"symbol":"BTC_USDT","price":"100","amount":"0.1","side":"buy",
                                "sequence":seq,"timestamp":"2026-10-07T13:00:00Z"})

    journal = tmp_path / "journal.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=tmp_path / "session.jsonl",
        transport_factory=OverLimitTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-source-completeness",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-source-ordering",
        max_records=3,
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "FORWARD_RECORD_BOUND_EXCEEDED"
    assert result.records_received == 3
    assert result.diagnostics == ({"max_records": 3},)
    assert not journal.exists()


def test_runner_blocks_before_network_or_session_without_verified_sequence_contract(tmp_path: Path):
    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("transport must not be constructed before sequence contract verification")

    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        transport_factory=MustNotRunTransport,
        ws_factory=FakeWS,
        max_runtime_seconds=1,
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED"
    assert result.run_id == "NOT_STARTED"
    assert result.records_received == 0
    assert result.diagnostics == ({
        "network_started": False,
        "session_written": False,
        "sequence_contract_evidence_required": True,
    },)
    assert not session.exists()
    assert not journal.exists()


def test_runner_requires_evidence_reference_even_when_verified_flag_is_true(tmp_path: Path):
    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "journal.jsonl",
        session_path=tmp_path / "session.jsonl",
        sequence_contract_verified=True,
        ws_factory=FakeWS,
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED"
    assert not (tmp_path / "session.jsonl").exists()


def test_runner_blocks_before_network_without_source_completeness_evidence(tmp_path: Path):
    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("transport must not be constructed before source completeness verification")

    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "journal.jsonl",
        session_path=tmp_path / "session.jsonl",
        transport_factory=MustNotRunTransport,
        ws_factory=FakeWS,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "SOURCE_COMPLETENESS_UNVERIFIED"
    assert result.run_id == "NOT_STARTED"
    assert result.diagnostics == ({
        "network_started": False,
        "session_written": False,
        "source_completeness_evidence_required": True,
    },)
    assert not (tmp_path / "session.jsonl").exists()
    assert not (tmp_path / "journal.jsonl").exists()



def test_runner_rejects_unregistered_caller_claims_before_network_or_session(tmp_path: Path):
    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("unregistered evidence must block before transport construction")

    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "journal.jsonl",
        session_path=tmp_path / "session.jsonl",
        transport_factory=MustNotRunTransport,
        ws_factory=FakeWS,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="caller-made-up:contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="caller-made-up:completeness",
        source_ordering_verified=True,
        source_ordering_evidence_ref="caller-made-up:ordering",
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "SOURCE_EVIDENCE_REF_NOT_REGISTERED"
    assert result.run_id == "NOT_STARTED"
    assert not (tmp_path / "session.jsonl").exists()
    assert not (tmp_path / "journal.jsonl").exists()


def test_runner_blocks_when_release_pin_is_unset(tmp_path: Path, monkeypatch):
    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("unset release pin must block before transport construction")

    monkeypatch.setattr(registry_module, "PINNED_SOURCE_EVIDENCE_REGISTRY_SHA256", "")
    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "journal.jsonl",
        session_path=tmp_path / "session.jsonl",
        transport_factory=MustNotRunTransport,
        ws_factory=FakeWS,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
        source_completeness_verified=True,
        source_completeness_evidence_ref="test-fixture:reviewed-source-completeness",
        source_ordering_verified=True,
        source_ordering_evidence_ref="test-fixture:reviewed-source-ordering",
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "SOURCE_EVIDENCE_REGISTRY_PIN_UNSET"
    assert result.run_id == "NOT_STARTED"
    assert not (tmp_path / "session.jsonl").exists()
    assert not (tmp_path / "journal.jsonl").exists()
