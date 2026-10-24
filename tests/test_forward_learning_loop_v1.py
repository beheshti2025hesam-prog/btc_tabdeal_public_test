import pytest

from forward.learning_loop_v1 import build_learning_report, report_json


def sample():
    return [
        {
            "event_id": f"e{i}",
            "decision": "LONG",
            "market_regime": "TREND",
            "decision_gate": "ENTRY",
            "outcome": "LOSS" if i < 5 else "WIN",
        }
        for i in range(1, 7)
    ] + [
        {
            "event_id": "reject-1",
            "decision": "NO_TRADE",
            "rejected_at": "RISK",
            "reason_codes": ["RR_TOO_LOW"],
            "outcome": None,
        }
    ]


def test_reports_loss_concentration_as_hypothesis_only():
    report = build_learning_report(sample(), min_group_size=5)
    assert report.eligible_closed_trade_count == 6
    assert report.decision_counts["NO_TRADE"] == 1
    assert any(
        hypothesis["type"] == "INVESTIGATE_LOSS_CONCENTRATION"
        and hypothesis["action"] == "RESEARCH_ONLY_NO_PARAMETER_CHANGE"
        for hypothesis in report.hypotheses
    )


def test_open_trade_excluded_from_closed_count():
    report = build_learning_report(
        sample() + [{"event_id": "open-1", "decision": "SHORT", "outcome": "OPEN"}]
    )
    assert report.eligible_closed_trade_count == 6
    assert report.excluded_unclosed_count == 1


def test_duplicate_events_fail_closed():
    records = [
        {"event_id": "x", "decision": "NO_TRADE"},
        {"event_id": "x", "decision": "NO_TRADE"},
    ]
    with pytest.raises(ValueError, match="duplicate_event_id"):
        build_learning_report(records)


@pytest.mark.parametrize(
    "record",
    [
        {"event_id": "x", "decision": "LONG", "source_period": "Historical"},
        {"event_id": "x", "decision": "LONG", "population": "winner"},
        {"event_id": "x", "decision": "LONG", "population": "SURVIVOR"},
    ],
)
def test_historical_or_survivor_population_forbidden(record):
    with pytest.raises(ValueError, match="HISTORICAL_POPULATION_FORBIDDEN"):
        build_learning_report([record])


def test_no_trade_cannot_have_trade_outcome():
    with pytest.raises(ValueError, match="NO_TRADE_CANNOT_HAVE_TRADE_OUTCOME"):
        build_learning_report(
            [{"event_id": "x", "decision": "NO_TRADE", "outcome": "WIN"}]
        )


def test_report_serialization_deterministic():
    assert report_json(build_learning_report(sample())) == report_json(
        build_learning_report(sample())
    )


def test_source_hash_is_independent_of_input_order():
    rows = sample()
    forward = build_learning_report(rows)
    reverse = build_learning_report(list(reversed(rows)))
    assert forward.source_sha256 == reverse.source_sha256
    assert report_json(forward) == report_json(reverse)


@pytest.mark.parametrize(
    ("record", "error"),
    [
        ({"event_id": "x", "decision": ["LONG"]}, "invalid_decision"),
        ({"event_id": "x", "decision": "LONG", "outcome": ["WIN"]}, "invalid_outcome"),
        ({"event_id": "x", "decision": "LONG", "market_regime": ["TREND"]}, "invalid_market_regime"),
        ({"event_id": "x", "decision": "LONG", "decision_gate": {"gate": "ENTRY"}}, "invalid_decision_gate"),
        ({"event_id": "x", "decision": "LONG", "metric": float("nan")}, "record_not_canonical_json"),
    ],
)
def test_malformed_input_fails_closed(record, error):
    with pytest.raises(ValueError, match=error):
        build_learning_report([record])


def test_cancelled_trade_is_neither_closed_performance_nor_open():
    report = build_learning_report(
        [
            {"event_id": "closed", "decision": "LONG", "outcome": "WIN"},
            {"event_id": "cancelled", "decision": "SHORT", "outcome": "CANCELLED"},
            {"event_id": "open", "decision": "SHORT", "outcome": "OPEN"},
        ]
    )
    assert report.eligible_closed_trade_count == 1
    assert report.excluded_unclosed_count == 1


def test_invalid_min_group_size_fails_closed():
    for value in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match="min_group_size"):
            build_learning_report([], min_group_size=value)



from datetime import datetime, timezone
import json

from forward.learning_loop_v1 import build_report_from_forward_evidence


def _decision_record(event_id="e-1", decision="LONG", observed_at="2026-10-24T10:00:00+00:00"):
    return {
        "event_id": event_id,
        "observed_at": observed_at,
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "market_regime": "TREND",
        "decision": decision,
        "evidence_source": "approved_forward_source_ref",
        "no_trade_reason": "RISK_NOT_APPROVED" if decision == "NO_TRADE" else None,
        "outcome": None,
        "closed_at": None,
    }


def _write_journal(path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\\n" for row in rows), encoding="utf-8")


def test_forward_evidence_reader_joins_immutable_outcome_by_event_id(tmp_path):
    journal = tmp_path / "journal.jsonl"
    outcomes = tmp_path / "outcomes"
    outcomes.mkdir()
    decision = _decision_record()
    _write_journal(journal, [decision])
    raw_decision_bytes = journal.read_bytes()
    (outcomes / "arbitrary-name.json").write_text(
        json.dumps({
            "event_id": "e-1",
            "outcome": "WIN",
            "closed_at": "2026-10-24T11:00:00+00:00",
            "realized_rr": 2.5,
        }),
        encoding="utf-8",
    )
    result = build_report_from_forward_evidence(
        journal, outcomes, now=datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    )
    assert result.report.eligible_closed_trade_count == 1
    assert result.report.decision_counts["LONG"] == 1
    assert result.evidence_manifest["decision_journal_sha256"]
    assert result.evidence_manifest["outcome_manifest_sha256"]
    assert result.evidence_manifest["execution_enabled"] is False
    assert result.evidence_manifest["orders_placed"] is False
    assert journal.read_bytes() == raw_decision_bytes
    assert result.report.source_sha256


def test_forward_evidence_reader_keeps_missing_outcomes_unclosed(tmp_path):
    journal = tmp_path / "journal.jsonl"
    outcomes = tmp_path / "outcomes"
    outcomes.mkdir()
    _write_journal(journal, [_decision_record()])
    result = build_report_from_forward_evidence(
        journal, outcomes, now=datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    )
    assert result.report.eligible_closed_trade_count == 0
    assert result.report.excluded_unclosed_count == 1
    assert result.evidence_manifest["outcome_artifact_count"] == 0


@pytest.mark.parametrize(
    ("artifact", "error"),
    [
        ({"event_id": "unknown", "outcome": "WIN", "closed_at": "2026-10-24T11:00:00+00:00"}, "UNKNOWN_DECISION_EVENT_ID"),
        ({"event_id": "e-1", "outcome": "WIN", "closed_at": "2026-10-24T09:00:00+00:00"}, "FORWARD_OUTCOME_CLOSE_TIME_INVALID"),
        ({"event_id": "e-1", "outcome": "WIN", "closed_at": "2026-10-24T13:00:00+00:00"}, "FORWARD_OUTCOME_CLOSE_TIME_INVALID"),
    ],
)
def test_forward_evidence_reader_rejects_unmatched_or_invalid_outcomes(tmp_path, artifact, error):
    journal = tmp_path / "journal.jsonl"
    outcomes = tmp_path / "outcomes"
    outcomes.mkdir()
    _write_journal(journal, [_decision_record()])
    (outcomes / "outcome.json").write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        build_report_from_forward_evidence(
            journal, outcomes, now=datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        )


def test_forward_evidence_reader_rejects_partial_journal_tail(tmp_path):
    journal = tmp_path / "journal.jsonl"
    outcomes = tmp_path / "outcomes"
    outcomes.mkdir()
    journal.write_text(json.dumps(_decision_record()), encoding="utf-8")
    with pytest.raises(ValueError, match="PARTIAL_TAIL"):
        build_report_from_forward_evidence(
            journal, outcomes, now=datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        )


def test_forward_evidence_reader_rejects_duplicate_decision_ids(tmp_path):
    journal = tmp_path / "journal.jsonl"
    outcomes = tmp_path / "outcomes"
    outcomes.mkdir()
    _write_journal(journal, [_decision_record(), _decision_record()])
    with pytest.raises(ValueError, match="DUPLICATE"):
        build_report_from_forward_evidence(
            journal, outcomes, now=datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        )


def test_forward_evidence_reader_rejects_outcome_for_no_trade(tmp_path):
    journal = tmp_path / "journal.jsonl"
    outcomes = tmp_path / "outcomes"
    outcomes.mkdir()
    _write_journal(journal, [_decision_record(decision="NO_TRADE")])
    (outcomes / "outcome.json").write_text(
        json.dumps({
            "event_id": "e-1",
            "outcome": "WIN",
            "closed_at": "2026-10-24T11:00:00+00:00",
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="FORWARD_OUTCOME_FOR_NON_TRADE_DECISION"):
        build_report_from_forward_evidence(
            journal, outcomes, now=datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        )
