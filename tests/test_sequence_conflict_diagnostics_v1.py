import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from forward.controlled_forward_observation_runner_v1 import ControlledForwardObservationRunnerV1
from forward.sequence_integrity_diagnostic_journal_v1 import SequenceIntegrityDiagnosticJournalV1
from forward.sequence_integrity_v1 import SequenceIntegrityV1


def test_conflicting_duplicate_reports_safe_field_diff_and_hashes():
    guard = SequenceIntegrityV1()
    first = {
        "source": "tabdeal_ws_forward_v1",
        "symbol": "BTC_USDT",
        "price": "100",
        "amount": "0.1",
        "side": "buy",
        "source_updated": "2026-10-09T17:00:00+00:00",
        "sequence": 41627925358,
    }
    conflicting = {**first, "price": "101"}

    assert guard.observe(first).status == "ACCEPTED"
    event = guard.observe(conflicting)

    assert event.status == "REJECT_STREAM"
    assert event.reason == "CONFLICTING_DUPLICATE_SEQUENCE"
    assert event.diagnostic["differing_fields"] == ["price"]
    assert event.diagnostic["first_values"] == {"price": "100"}
    assert event.diagnostic["conflicting_values"] == {"price": "101"}
    assert event.diagnostic["first_payload_sha256"] != event.diagnostic["conflicting_payload_sha256"]


def test_runner_never_reaches_conflict_transport_without_authoritative_verifier(tmp_path: Path):
    class MustNotRunConflictTransport:
        def __init__(self, **kwargs):
            raise AssertionError("transport must not be constructed while sequence semantics are unverified")

    diagnostics_path = tmp_path / "sequence_integrity_diagnostics_v1.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "observations.jsonl",
        session_path=tmp_path / "sessions.jsonl",
        diagnostics_path=diagnostics_path,
        transport_factory=MustNotRunConflictTransport,
        ws_factory=object,
        max_runtime_seconds=1,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
    )
    result = runner.run(started_at=datetime(2026, 10, 9, 17, 1, tzinfo=timezone.utc))

    assert result.status == "BLOCKED"
    assert result.reason == "AUTHORITATIVE_SEQUENCE_EVIDENCE_VERIFIER_NOT_IMPLEMENTED"
    assert result.run_id == "NOT_STARTED"
    assert result.snapshot_id is None
    assert result.records_received == 0
    assert not (tmp_path / "observations.jsonl").exists()
    assert not (tmp_path / "sessions.jsonl").exists()
    assert not diagnostics_path.exists()


def test_diagnostic_journal_hash_chain_and_fail_closed_corruption(tmp_path: Path):
    path = tmp_path / "diagnostics.jsonl"
    journal = SequenceIntegrityDiagnosticJournalV1(path)
    event = {"sequence": 7, "status": "REJECT_STREAM", "reason": "CONFLICTING_DUPLICATE_SEQUENCE"}

    first = journal.append_blocked_run(
        run_id="OBS-1",
        observed_at_utc="2026-10-09T17:00:00+00:00",
        reason="SEQUENCE_UNSAFE",
        diagnostics=[event],
    )
    second = journal.append_blocked_run(
        run_id="OBS-2",
        observed_at_utc="2026-10-09T17:01:00+00:00",
        reason="SEQUENCE_UNSAFE",
        diagnostics=[event],
    )

    assert first is not None and second is not None
    assert second["previous_record_sha256"] == first["record_sha256"]
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    payload = json.loads(lines[1])
    digest = payload.pop("record_sha256")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == digest

    path.write_text(path.read_text(encoding="utf-8") + "{broken}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="invalid JSON"):
        journal.append_blocked_run(
            run_id="OBS-3",
            observed_at_utc="2026-10-09T17:02:00+00:00",
            reason="SEQUENCE_UNSAFE",
            diagnostics=[event],
        )


def test_metadata_overflow_transport_is_not_constructed_before_sequence_gate(tmp_path: Path):
    class MustNotRunMetadataOverflowTransport:
        def __init__(self, **kwargs):
            raise AssertionError("metadata overflow test transport must remain unreachable before evidence verification")

    journal_path = tmp_path / "observations.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=journal_path,
        session_path=tmp_path / "sessions.jsonl",
        transport_factory=MustNotRunMetadataOverflowTransport,
        ws_factory=object,
        max_runtime_seconds=1,
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:authoritative-contract",
    )
    result = runner.run(started_at=datetime(2026, 10, 9, 17, 1, tzinfo=timezone.utc))

    assert result.status == "BLOCKED"
    assert result.reason == "AUTHORITATIVE_SEQUENCE_EVIDENCE_VERIFIER_NOT_IMPLEMENTED"
    assert result.records_received == 0
    assert result.snapshot_id is None
    assert not journal_path.exists()
