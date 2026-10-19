from datetime import datetime, timezone
from pathlib import Path

import pytest
import forward.controlled_forward_observation_runner_v1 as runner_module
from forward.controlled_forward_observation_runner_v1 import (
    ControlledForwardObservationRunnerV1,
)



@pytest.fixture(autouse=True)
def use_test_only_sequence_contract_reference(monkeypatch):
    # Test fixtures explicitly simulate a reviewed reference. Production remains
    # blocked because the module-level approved reference is None.
    monkeypatch.setattr(
        runner_module,
        "VERIFIED_UPSTREAM_SEQUENCE_CONTRACT_EVIDENCE_REF",
        "test-fixture:authoritative-contract",
    )


class FakeWS:
    def __init__(self, url, on_open, on_message):
        self.url = url
        self.on_open = on_open
        self.on_message = on_message

    def run_forever(self, **kwargs):
        self.on_open(self)
        for seq, price in ((100, "100.0"), (101, "101.0"), (102, "102.0")):
            self.on_message(self, '{"trade": {"symbol":"BTC_USDT","price":"%s","amount":"0.1","side":"buy","sequence":%d,"updated":"2026-10-07T13:00:00Z"}}' % (price, seq))

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

def test_arbitrary_nonempty_reference_cannot_unlock_production_default(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        runner_module,
        "VERIFIED_UPSTREAM_SEQUENCE_CONTRACT_EVIDENCE_REF",
        None,
    )
    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("arbitrary evidence text must not open a transport")

    session = tmp_path / "session.jsonl"
    journal = tmp_path / "journal.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        transport_factory=MustNotRunTransport,
        ws_factory=FakeWS,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="https://example.invalid/fake-proof",
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED"
    assert result.diagnostics[0]["network_started"] is False
    assert result.diagnostics[0]["session_written"] is False
    assert not session.exists()
    assert not journal.exists()

def test_nonmatching_reference_cannot_unlock_a_different_reviewed_pin(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        runner_module,
        "VERIFIED_UPSTREAM_SEQUENCE_CONTRACT_EVIDENCE_REF",
        "reviewed-artifact:sha256:approved",
    )

    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("a reference that differs from the reviewed pin must not open transport")

    session = tmp_path / "session.jsonl"
    journal = tmp_path / "journal.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        transport_factory=MustNotRunTransport,
        ws_factory=FakeWS,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="reviewed-artifact:sha256:unapproved",
    )
    result = runner.run(started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED"
    assert result.diagnostics[0]["network_started"] is False
    assert result.diagnostics[0]["session_written"] is False
    assert not session.exists()
    assert not journal.exists()
