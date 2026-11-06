import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from forward.controlled_forward_observation_runner_v1 import ControlledForwardObservationRunnerV1
from forward.sequence_integrity_diagnostic_journal_v1 import SequenceIntegrityDiagnosticJournalV1
from forward.sequence_integrity_v1 import SequenceIntegrityV1


def allow_sequence_capabilities(monkeypatch):
    allowed = {"safe": True, "reason": "SEQUENCE_CAPABILITIES_VERIFIED"}
    for module in (
        "forward.controlled_forward_observation_runner_v1",
        "forward.forward_observation_path_v1",
        "forward.sequence_candle_integration_v1",
        "forward.forward_tabdeal_ingestion_v1",
    ):
        monkeypatch.setattr(f"{module}.evaluate_tabdeal_trade_sequence_capabilities", lambda: allowed)


def test_conflicting_duplicate_reports_safe_field_diff_and_hashes():
    guard = SequenceIntegrityV1()
    first = {
        "source": "tabdeal_ws_forward_v1", "symbol": "BTC_USDT",
        "price": "100", "amount": "0.1", "side": "buy", "sequence": 41627925358,
    }
    conflicting = {**first, "price": "101"}
    assert guard.observe(first).status == "ACCEPTED"
    event = guard.observe(conflicting)
    assert event.status == "REJECT_STREAM"
    assert event.reason == "CONFLICTING_DUPLICATE_SEQUENCE"
    assert event.diagnostic["differing_fields"] == ["price"]
    assert event.diagnostic["first_payload_sha256"] != event.diagnostic["conflicting_payload_sha256"]


def test_runner_persists_conflict_fingerprint_only_under_positive_test_capability_fixture(tmp_path: Path, monkeypatch):
    allow_sequence_capabilities(monkeypatch)

    class ConflictTransport:
        def __init__(self, on_record, **kwargs):
            self.on_record = on_record

        def run_once(self):
            first = {
                "symbol": "BTC_USDT", "price": "100", "amount": "0.1",
                "side": "buy", "sequence": 41627925358, "timestamp": "2026-10-09T17:00:00Z",
            }
            self.on_record(first)
            self.on_record({**first, "price": "101"})

    diagnostics_path = tmp_path / "sequence_integrity_diagnostics_v1.jsonl"
    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "observations.jsonl",
        session_path=tmp_path / "sessions.jsonl",
        diagnostics_path=diagnostics_path,
        transport_factory=ConflictTransport,
        ws_factory=object,
        max_runtime_seconds=1,
    )
    result = runner.run(started_at=datetime(2026, 10, 9, 17, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "SEQUENCE_UNSAFE"
    assert result.records_received == 2
    rows = [json.loads(line) for line in diagnostics_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    diagnostic = rows[0]["sequence_events"][0]["diagnostic"]
    assert diagnostic["differing_fields"] == ["price"]
    assert diagnostic["first_payload_sha256"] != diagnostic["conflicting_payload_sha256"]


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
    try:
        journal.append_blocked_run(
            run_id="OBS-3", observed_at_utc="2026-10-09T17:02:00+00:00",
            reason="SEQUENCE_UNSAFE", diagnostics=[event],
        )
    except RuntimeError as exc:
        assert "invalid JSON" in str(exc)
    else:
        raise AssertionError("corrupt diagnostic journal must fail closed")


def test_metadata_bound_is_enforced_only_after_registry_allows_transport(tmp_path: Path, monkeypatch):
    allow_sequence_capabilities(monkeypatch)

    class MetadataOverflowTransport:
        def __init__(self, on_record, on_frame_metadata, **kwargs):
            self.on_record = on_record
            self.on_frame_metadata = on_frame_metadata

        def run_once(self):
            for sequence in range(50_001):
                self.on_frame_metadata({
                    "normalized_sequence": sequence,
                    "raw_frame_sha256": f"{sequence:064x}",
                })

    runner = ControlledForwardObservationRunnerV1(
        journal_path=tmp_path / "observations.jsonl",
        session_path=tmp_path / "sessions.jsonl",
        transport_factory=MetadataOverflowTransport,
        ws_factory=object,
        max_runtime_seconds=1,
    )
    result = runner.run(started_at=datetime(2026, 10, 9, 17, 1, tzinfo=timezone.utc))
    assert result.status == "BLOCKED"
    assert result.reason == "TRANSPORT_METADATA_BOUND_EXCEEDED"
    assert result.records_received == 0
