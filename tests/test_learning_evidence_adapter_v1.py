import json

import pytest

from forward.learning_evidence_adapter_v1 import (
    build_forward_learning_report,
    record_signal_decision,
)


def record_decision(path, decision="NO_TRADE"):
    return record_signal_decision(
        path,
        decision=decision,
        observed_at="2026-10-24T10:00:00+00:00",
        symbol="BTCUSDT",
        timeframe="15m",
        source="binance_native_ohlcv_v1",
        product="spot",
        response_sha256="a" * 64,
        htf_response_sha256="b" * 64,
        strategy_evidence_sha256="c" * 64,
        policy_version="hes-strategy-policy-v1",
        status="BLOCKED" if decision == "NO_TRADE" else "READY",
        market_regime="UNKNOWN",
        rejected_at="RISK" if decision == "NO_TRADE" else "",
        reason_codes=["RISK_CONTEXT_UNKNOWN"] if decision == "NO_TRADE" else [],
    )


def write_outcome(directory, event_id, outcome="WIN", closed_at="2026-10-24T11:00:00+00:00"):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "outcome.json"
    path.write_text(json.dumps({
        "event_id": event_id,
        "outcome": outcome,
        "closed_at": closed_at,
        "source_period": "forward",
        "population": "forward",
        "realized_rr": 2.5,
    }), encoding="utf-8")
    return path


def test_signal_decision_journal_is_idempotent_and_outcome_free(tmp_path):
    path = tmp_path / "decisions.jsonl"
    first = record_decision(path)
    second = record_decision(path)
    assert first.status == "RECORDED"
    assert second.status == "ALREADY_RECORDED"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["decision"] == "NO_TRADE"
    assert rows[0]["evidence_source"]
    assert rows[0]["no_trade_reason"]
    assert "outcome" not in rows[0]
    assert rows[0]["execution"] == "OFF"
    assert path.read_bytes().endswith(b"\n")


def test_existing_forward_evidence_reader_joins_separate_outcome(tmp_path):
    journal = tmp_path / "decisions.jsonl"
    outcomes = tmp_path / "outcomes"
    decision = record_decision(journal, decision="LONG")
    write_outcome(outcomes, decision.event_id)
    result = build_forward_learning_report(
        journal, outcomes, now=__import__("datetime").datetime(2026, 10, 24, 12, tzinfo=__import__("datetime").timezone.utc)
    )
    assert result.report.eligible_closed_trade_count == 1
    assert result.report.decision_counts["LONG"] == 1
    assert result.evidence_manifest["decision_journal_sha256"]
    assert result.evidence_manifest["outcome_manifest_sha256"]
    assert result.evidence_manifest["execution_enabled"] is False
    assert result.evidence_manifest["orders_placed"] is False


def test_missing_outcome_remains_unclosed(tmp_path):
    journal = tmp_path / "decisions.jsonl"
    outcomes = tmp_path / "outcomes"
    outcomes.mkdir()
    record_decision(journal, decision="LONG")
    result = build_forward_learning_report(
        journal, outcomes, now=__import__("datetime").datetime(2026, 10, 24, 12, tzinfo=__import__("datetime").timezone.utc)
    )
    assert result.report.eligible_closed_trade_count == 0
    assert result.report.excluded_unclosed_count == 1
    assert result.evidence_manifest["outcome_artifact_count"] == 0


def test_no_trade_cannot_receive_outcome(tmp_path):
    journal = tmp_path / "decisions.jsonl"
    outcomes = tmp_path / "outcomes"
    decision = record_decision(journal)
    write_outcome(outcomes, decision.event_id)
    with pytest.raises(ValueError, match="FORWARD_OUTCOME_FOR_NON_TRADE_DECISION"):
        build_forward_learning_report(
            journal, outcomes, now=__import__("datetime").datetime(2026, 10, 24, 12, tzinfo=__import__("datetime").timezone.utc)
        )


def test_conflicting_output_for_identical_evidence_fails_closed(tmp_path):
    path = tmp_path / "decisions.jsonl"
    record_decision(path, decision="LONG")
    with pytest.raises(ValueError, match="conflicting_duplicate_decision_event"):
        record_decision(path, decision="SHORT")


def test_malformed_decision_and_hashes_fail_closed(tmp_path):
    common = dict(
        observed_at="2026-10-24T10:00:00+00:00",
        symbol="BTCUSDT", timeframe="15m", source="binance_native_ohlcv_v1",
        product="spot", response_sha256="bad", htf_response_sha256="b" * 64,
        strategy_evidence_sha256=None, policy_version="hes-strategy-policy-v1",
        status="BLOCKED", market_regime="UNKNOWN", rejected_at="RISK",
        reason_codes=["RISK_CONTEXT_UNKNOWN"],
    )
    with pytest.raises(ValueError, match="invalid_decision"):
        record_signal_decision(tmp_path / "bad.jsonl", decision=["LONG"], **common)
    with pytest.raises(ValueError, match="invalid_response_sha256"):
        record_signal_decision(tmp_path / "bad.jsonl", decision="NO_TRADE", **common)


def test_future_outcome_and_historical_population_are_rejected(tmp_path):
    journal = tmp_path / "decisions.jsonl"
    outcomes = tmp_path / "outcomes"
    decision = record_decision(journal, decision="LONG")
    write_outcome(outcomes, decision.event_id, closed_at="2026-10-24T13:00:00+00:00")
    with pytest.raises(ValueError, match="FORWARD_OUTCOME_CLOSE_TIME_INVALID"):
        build_forward_learning_report(
            journal, outcomes, now=__import__("datetime").datetime(2026, 10, 24, 12, tzinfo=__import__("datetime").timezone.utc)
        )
