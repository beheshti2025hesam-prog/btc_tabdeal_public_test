import json
from hashlib import sha256

import pytest

from forward.forward_observation_writer_v1 import canonical_json
from forward.learning_evidence_adapter_v1 import (
    build_report_from_artifacts,
    record_signal_decision,
    record_forward_outcome,
)


def record_decision(path, decision="NO_TRADE"):
    return record_signal_decision(
        path,
        decision=decision,
        observed_at="2026-10-24T12:00:00+00:00",
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


def outcome_record(decision_event_id, decision_digest, outcome="WIN"):
    row = {
        "artifact_type": "FORWARD_OUTCOME",
        "outcome_event_id": "outcome-1",
        "decision_event_id": decision_event_id,
        "outcome": outcome,
        "closed_at": "2026-10-24T12:30:00+00:00",
        "source_period": "forward",
        "execution": "OFF",
        "evidence_ref": "independent-forward-close-record",
        "evidence_sha256": "d" * 64,
        "decision_digest": decision_digest,
    }
    row["digest"] = sha256(canonical_json(row).encode("utf-8")).hexdigest()
    return row


def read_decisions(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_signal_decision_journal_is_idempotent_and_outcome_free(tmp_path):
    path = tmp_path / "decisions.jsonl"
    first = record_decision(path)
    second = record_decision(path)
    assert first.status == "RECORDED"
    assert second.status == "ALREADY_RECORDED"
    records = read_decisions(path)
    assert len(records) == 1
    assert records[0]["decision"] == "NO_TRADE"
    assert "outcome" not in records[0]
    assert records[0]["execution"] == "OFF"


def test_separate_verified_outcome_joins_to_decision(tmp_path):
    path = tmp_path / "decisions.jsonl"
    recorded = record_decision(path, decision="LONG")
    report = build_report_from_artifacts(
        read_decisions(path),
        [outcome_record(recorded.event_id, recorded.digest, "LOSS")],
        min_group_size=1,
    )
    assert report.eligible_closed_trade_count == 1
    assert report.decision_counts["LONG"] == 1
    assert any(item["outcome"] == "LOSS" for item in report.attribution)


def test_no_trade_cannot_receive_closed_trade_outcome(tmp_path):
    path = tmp_path / "decisions.jsonl"
    recorded = record_decision(path)
    with pytest.raises(ValueError, match="NO_TRADE_CANNOT_HAVE_TRADE_OUTCOME"):
        build_report_from_artifacts(
            read_decisions(path),
            [outcome_record(recorded.event_id, recorded.digest, "WIN")],
        )


def test_unknown_decision_reference_is_rejected(tmp_path):
    path = tmp_path / "decisions.jsonl"
    record_decision(path, decision="LONG")
    with pytest.raises(ValueError, match="outcome_without_known_forward_decision"):
        build_report_from_artifacts(read_decisions(path), [outcome_record("missing-event", "d" * 64)])


def test_modified_decision_digest_is_rejected(tmp_path):
    path = tmp_path / "decisions.jsonl"
    record_decision(path, decision="LONG")
    rows = read_decisions(path)
    rows[0]["decision"] = "SHORT"
    with pytest.raises(ValueError, match="decision_digest_mismatch"):
        build_report_from_artifacts(rows, [])


def test_modified_outcome_digest_is_rejected(tmp_path):
    path = tmp_path / "decisions.jsonl"
    recorded = record_decision(path, decision="LONG")
    outcome = outcome_record(recorded.event_id, recorded.digest)
    outcome["outcome"] = "LOSS"
    with pytest.raises(ValueError, match="outcome_digest_mismatch"):
        build_report_from_artifacts(read_decisions(path), [outcome])


def test_historical_outcome_is_rejected(tmp_path):
    path = tmp_path / "decisions.jsonl"
    recorded = record_decision(path, decision="LONG")
    outcome = outcome_record(recorded.event_id, recorded.digest)
    outcome["source_period"] = "historical"
    outcome.pop("digest")
    outcome["digest"] = sha256(canonical_json(outcome).encode("utf-8")).hexdigest()
    with pytest.raises(ValueError, match="outcome_population_not_forward_only"):
        build_report_from_artifacts(read_decisions(path), [outcome])


def test_conflicting_duplicate_decision_event_fails_closed(tmp_path):
    path = tmp_path / "decisions.jsonl"
    record_decision(path, decision="LONG")
    with pytest.raises(ValueError, match="conflicting_duplicate_decision_event"):
        # Same observation identity but a changed policy result is not silently overwritten.
        record_signal_decision(
            path,
            decision="SHORT",
            observed_at="2026-10-24T12:00:00+00:00",
            symbol="BTCUSDT",
            timeframe="15m",
            source="binance_native_ohlcv_v1",
            product="spot",
            response_sha256="a" * 64,
            htf_response_sha256="b" * 64,
            strategy_evidence_sha256="c" * 64,
            policy_version="hes-strategy-policy-v1",
            status="READY",
            market_regime="UNKNOWN",
            rejected_at="",
            reason_codes=[],
        )


def test_outcome_writer_requires_existing_long_short_decision_and_is_idempotent(tmp_path):
    decision_path = tmp_path / "decisions.jsonl"
    outcome_path = tmp_path / "outcomes.jsonl"
    recorded = record_decision(decision_path, decision="LONG")
    kwargs = dict(
        decision_journal_path=decision_path,
        decision_event_id=recorded.event_id,
        outcome="WIN",
        closed_at="2026-10-24T12:30:00+00:00",
        evidence_ref="independent-forward-close-record",
        evidence_sha256="e" * 64,
    )
    first = record_forward_outcome(outcome_path, **kwargs)
    second = record_forward_outcome(outcome_path, **kwargs)
    assert first.status == "RECORDED"
    assert second.status == "ALREADY_RECORDED"
    rows = [json.loads(line) for line in outcome_path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["decision_digest"] == recorded.digest


def test_outcome_writer_rejects_predecision_close_and_no_trade(tmp_path):
    decision_path = tmp_path / "decisions.jsonl"
    outcome_path = tmp_path / "outcomes.jsonl"
    with pytest.raises(ValueError, match="NO_TRADE_CANNOT_HAVE_TRADE_OUTCOME"):
        record_forward_outcome(
            outcome_path,
            decision_journal_path=decision_path,
            decision_event_id=record_decision(decision_path).event_id,
            outcome="WIN",
            closed_at="2026-10-24T12:30:00+00:00",
            evidence_ref="independent-forward-close-record",
            evidence_sha256="e" * 64,
        )
    decision_path_long = tmp_path / "decisions-long.jsonl"
    recorded = record_decision(decision_path_long, decision="LONG")
    with pytest.raises(ValueError, match="outcome_precedes_decision"):
        record_forward_outcome(
            outcome_path,
            decision_journal_path=decision_path_long,
            decision_event_id=recorded.event_id,
            outcome="LOSS",
            closed_at="2026-10-24T11:00:00+00:00",
            evidence_ref="independent-forward-close-record",
            evidence_sha256="e" * 64,
        )
