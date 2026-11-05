import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from forward.controlled_forward_observation_runner_v1 import ControlledForwardObservationRunnerV1
from forward.sequence_integrity_diagnostic_journal_v1 import SequenceIntegrityDiagnosticJournalV1
from forward.sequence_integrity_v1 import SequenceIntegrityV1


def test_low_level_sequence_state_machine_only_reports_a_conflict_when_explicitly_used():
    guard = SequenceIntegrityV1()
    first = {
        "source": "test_fixture_with_explicit_sequence_contract",
        "symbol": "BTC_USDT",
        "price": "100",
        "amount": "0.1",
        "side": "buy",
        "sequence": 41627925358,
    }
    conflicting = {**first, "price": "101"}
    assert guard.observe(first).status == "ACCEPTED"
    event = guard.observe(conflicting)
    assert event.status == "REJECT_STREAM"
    assert event.reason == "CONFLICTING_DUPLICATE_SEQUENCE"
    assert event.diagnostic["differing_fields"] == ["price"]
    assert event.diagnostic["first_payload_sha256"] != event.diagnostic["conflicting_payload_sha256"]


def test_tabdeal_runner_blocks_before_transport_and_diagnostic_write_while_capabilities_unknown(tmp_path: Path):
    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("transport must not be constructed before registry capability proof")
    diagnostics_path = tmp_path / "sequence_integrity_diagnostics_v1.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "observations.jsonl",
        session_path=tmp_path / "sessions.jsonl",
        diagnostics_path=diagnostics_path,
        transport_factory=MustNotRunTransport,
        ws_factory=object,
        max_runtime_seconds=1,
    )
    result = runner.run(started_at=datetime(2026, 10, 9, 17, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "SEQUENCE_CAPABILITIES_UNVERIFIED"
    assert result.run_id == "NOT_STARTED"
    assert result.records_received == 0
    assert result.diagnostics[0]["network_started"] is False
    assert result.diagnostics[0]["session_written"] is False
    assert not (tmp_path / "observations.jsonl").exists()
    assert not (tmp_path / "sessions.jsonl").exists()
    assert not diagnostics_path.exists()


def test_diagnostic_journal_hash_chain_and_fail_closed_corruption(tmp_path: Path):
    path = tmp_path / "diagnostics.jsonl"
    journal = SequenceIntegrityDiagnosticJournalV1(path)
    event = {"sequence": 7, "status": "REJECT_STREAM", "reason": "CONFLICTING_DUPLICATE_SEQUENCE"}
    first = journal.append_blocked_run(
        run_id="OBS-1", observed_at_utc="2026-10-09T17:00:00+00:00",
        reason="SEQUENCE_UNSAFE", diagnostics=[event],
    )
    second = journal.append_blocked_run(
        run_id="OBS-2", observed_at_utc="2026-10-09T17:01:00+00:00",
        reason="SEQUENCE_UNSAFE", diagnostics=[event],
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
            run_id="OBS-3", observed_at_utc="2026-10-09T17:02:00+00:00",
            reason="SEQUENCE_UNSAFE", diagnostics=[event],
        )


def test_metadata_bound_is_not_reached_because_runner_blocks_before_network(tmp_path: Path):
    class MustNotRunTransport:
        def __init__(self, **kwargs):
            raise AssertionError("metadata callback must not be invoked while capabilities are unknown")
    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "observations.jsonl",
        session_path=tmp_path / "sessions.jsonl",
        transport_factory=MustNotRunTransport,
        ws_factory=object,
        max_runtime_seconds=1,
    )
    result = runner.run(started_at=datetime(2026, 10, 9, 17, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "SEQUENCE_CAPABILITIES_UNVERIFIED"
    assert result.records_received == 0
    assert result.diagnostics[0]["network_started"] is False
