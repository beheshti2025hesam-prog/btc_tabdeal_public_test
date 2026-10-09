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


def test_runner_persists_conflict_fingerprint_and_still_blocks(tmp_path: Path):
    class ConflictTransport:
        def __init__(self, on_record, on_frame_metadata, **kwargs):
            self.on_record = on_record
            self.on_frame_metadata = on_frame_metadata

        def run_once(self):
            base = {
                "symbol": "BTC_USDT",
                "amount": "0.1",
                "side": "buy",
                "sequence": 41627925358,
                "timestamp": "2026-10-09T17:00:00+00:00",
            }
            for index, price in enumerate(("100", "101")):
                self.on_frame_metadata({
                    "schema": "hes_transport_frame_fingerprint_v1",
                    "raw_frame_sha256": f"frame-hash-{index}",
                    "received_at_utc": f"2026-10-09T17:00:0{index}+00:00",
                    "receive_monotonic_ns": 1000 + index,
                    "outer_keys": ["trade"],
                    "trade_keys": ["amount", "price", "sequence", "side", "symbol", "timestamp"],
                    "sequence_field_path": "trade.sequence",
                    "sequence_value_type": "int",
                    "sequence_value": 41627925358,
                })
                self.on_record({**base, "price": price})

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
    assert result.snapshot_id is None
    assert not (tmp_path / "observations.jsonl").exists()
    assert diagnostics_path.exists()
    record = json.loads(diagnostics_path.read_text(encoding="utf-8").splitlines()[0])
    conflict = next(
        event for event in record["sequence_events"]
        if event.get("reason") == "CONFLICTING_DUPLICATE_SEQUENCE"
    )
    assert conflict["diagnostic"]["differing_fields"] == ["price"]
    fingerprints = conflict["transport_frame_fingerprints"]
    assert len(fingerprints) == 2
    assert fingerprints[0]["raw_frame_sha256"] != fingerprints[1]["raw_frame_sha256"]
    assert all(item["sequence_field_path"] == "trade.sequence" for item in fingerprints)
    assert all("price" not in item and "amount" not in item for item in fingerprints)
    assert any(item.get("diagnostic_persistence") == "PERSISTED" for item in result.diagnostics)


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
