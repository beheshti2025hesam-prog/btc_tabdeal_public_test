"""Adversarial regression tests for the sequence-evidence fail-closed gate.

These tests prove only that caller-controlled flags/strings cannot unlock transport.
They do not prove Tabdeal connectivity or protocol sequence semantics.
"""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from forward.controlled_forward_observation_runner_v1 import (
    ControlledForwardObservationRunnerV1,
)


class MustNotRunTransport:
    def __init__(self, **kwargs):
        raise AssertionError("transport must never be constructed without verified evidence")


class MustNotRunWS:
    def __init__(self, *args, **kwargs):
        raise AssertionError("websocket factory must never be invoked without verified evidence")


@pytest.mark.parametrize(
    ("verified", "evidence_ref"),
    [
        (True, "test-fixture:authoritative-contract"),
        (True, "anything"),
        (True, "/tmp/fake-evidence.json"),
        (True, "sha256:" + "a" * 64),
        (False, "test-fixture:authoritative-contract"),
        (True, ""),
        (True, "   "),
        (True, None),
        (False, None),
    ],
)
def test_caller_assertions_never_unlock_transport_or_session(
    tmp_path: Path, verified: bool, evidence_ref: str | None
):
    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        transport_factory=MustNotRunTransport,
        ws_factory=MustNotRunWS,
        sequence_contract_verified=verified,
        sequence_contract_evidence_ref=evidence_ref,
    )

    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )

    assert result.status == "BLOCKED"
    assert result.reason == "AUTHORITATIVE_SEQUENCE_EVIDENCE_VERIFIER_NOT_IMPLEMENTED"
    assert result.run_id == "NOT_STARTED"
    assert result.records_received == 0
    assert result.snapshot_id is None
    assert result.diagnostics == ({
        "network_started": False,
        "session_written": False,
        "sequence_contract_evidence_required": True,
        "caller_assertions_ignored": True,
        "authoritative_verifier_implemented": False,
    },)
    assert not session.exists()
    assert not journal.exists()


def test_missing_contract_evidence_fails_closed_before_side_effects(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    session = tmp_path / "session.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal,
        session_path=session,
        transport_factory=MustNotRunTransport,
        ws_factory=MustNotRunWS,
    )

    result = runner.run(
        started_at=datetime(2026, 10, 7, 13, 1, tzinfo=timezone.utc)
    )

    assert result.status == "BLOCKED"
    assert result.reason == "AUTHORITATIVE_SEQUENCE_EVIDENCE_VERIFIER_NOT_IMPLEMENTED"
    assert result.diagnostics[0]["network_started"] is False
    assert result.diagnostics[0]["session_written"] is False
    assert not session.exists()
    assert not journal.exists()
