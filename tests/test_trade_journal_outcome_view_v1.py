from __future__ import annotations

from datetime import datetime, timezone

from forward.trade_journal_outcome_view_v1 import read_outcome_projection


def sample_decisions():
    return {
        "schema": "hes.trade_journal_view.v1",
        "status": "VERIFIED",
        "count": 1,
        "truncated": False,
        "events": [{
            "event_id": "decision-1",
            "observed_at": "2026-10-25T10:00:00+00:00",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "decision": "LONG",
            "decision_gate": "RISK",
            "rejected_at": "—",
            "reason_codes": [],
            "execution": "OFF",
            "realized_outcome": "NOT_LINKED",
        }],
    }


def test_missing_outcome_dir_displays_unknown_without_inference(tmp_path, monkeypatch):
    import forward.trade_journal_outcome_view_v1 as view
    monkeypatch.setattr(view, "read_decision_journal", lambda *a, **k: sample_decisions())
    result = read_outcome_projection(tmp_path / "decision.jsonl", None)
    assert result["status"] == "OUTCOMES_NOT_CONFIGURED"
    event = result["events"][0]
    assert event["outcome"] == "NOT_LINKED"
    assert event["realized_rr"] == "UNKNOWN"
    assert event["fees"] == event["funding"] == event["realized_pnl"] == "UNKNOWN"
    assert event["pnl_evidence"] == "NOT_LINKED"
    assert result["execution_enabled"] is False
    assert result["outcomes_inferred"] is False


def test_existing_reader_join_is_projected_without_changing_contract(tmp_path, monkeypatch):
    import forward.trade_journal_outcome_view_v1 as view

    class Report:
        evidence_manifest = {
            "outcome_artifact_count": 1,
            "outcome_manifest_sha256": "a" * 64,
            "decision_journal_sha256": "b" * 64,
        }
        rows = ({
            "event_id": "decision-1",
            "observed_at": "2026-10-25T10:00:00+00:00",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "decision": "LONG",
            "outcome": "WIN",
            "closed_at": "2026-10-25T11:00:00+00:00",
            "realized_rr": 2.25,
            "outcome_artifact_sha256": "c" * 64,
        },)

    monkeypatch.setattr(view, "build_report_from_forward_evidence", lambda *a, **k: Report())
    outcome_dir = tmp_path / "outcomes"
    outcome_dir.mkdir()
    result = read_outcome_projection(
        tmp_path / "decision.jsonl", outcome_dir,
        now=datetime(2026, 10, 25, 12, tzinfo=timezone.utc),
    )
    event = result["events"][0]
    assert result["status"] == "VERIFIED"
    assert event["outcome"] == "WIN"
    assert event["realized_rr"] == 2.25
    assert event["outcome_artifact_sha256"] == "c" * 64
    assert event["fees"] == event["funding"] == event["realized_pnl"] == "UNKNOWN"
    assert result["outcomes_inferred"] is False


def test_invalid_outcome_directory_fails_closed(tmp_path):
    from forward.trade_journal_outcome_view_v1 import OutcomeProjectionError
    import pytest
    with pytest.raises(OutcomeProjectionError, match="outcome_directory_missing_or_unsafe"):
        read_outcome_projection(tmp_path / "decision.jsonl", tmp_path / "missing")
