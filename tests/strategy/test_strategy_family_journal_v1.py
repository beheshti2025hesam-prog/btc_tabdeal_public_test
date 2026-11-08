import json

import pytest

from forward.strategy_family_journal_v1 import (
    FAMILY_FILES,
    sync_strategy_family_result_journals,
)
from forward.strategy_family_router_v1 import route_strategy_family


def _candidate(candidate_id, family_regime=None):
    payload = {
        "candidate_event_id": candidate_id,
        "event_id": candidate_id,
        "observed_at": "2026-11-08T08:00:00+00:00",
        "candidate_time": 1_794_123_600,
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "direction": "LONG",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": 103.0,
        "rr": 3.0,
        "final_gate_decision": "NO_TRADE",
        "preapproval_paper_eligible": False,
        "execution_enabled": False,
        "orders_placed": False,
    }
    if family_regime is not None:
        route = route_strategy_family(
            source="gateio_public_spot",
            symbol="BTC_USDT",
            timeframe="15m",
            regime=family_regime,
        ).as_dict()
        payload["gate_evidence"] = {"strategy_family_route": route}
    return payload


def _outcome(event_id, candidate_id, outcome):
    return {
        "event_id": event_id,
        "candidate_event_id": candidate_id,
        "resolved_at": "2026-11-08T09:00:00+00:00",
        "candidate_time": 1_794_123_600,
        "direction": "LONG",
        "entry": 100.0,
        "stop_loss": 99.0,
        "take_profit": 103.0,
        "outcome": outcome,
        "reason": "TEST_FIXTURE",
        "performance_eligible": False,
        "preapproval_paper_eligible": False,
        "execution_enabled": False,
        "orders_placed": False,
    }


def _write(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_trend_and_range_results_are_projected_to_separate_idempotent_journals(tmp_path):
    candidates = tmp_path / "candidates.jsonl"
    outcomes = tmp_path / "outcomes.jsonl"
    _write(candidates, [
        _candidate("trend-candidate", "UPTREND"),
        _candidate("range-candidate", "RANGE"),
        _candidate("legacy-candidate"),
    ])
    _write(outcomes, [
        _outcome("trend-outcome", "trend-candidate", "losses"),
        _outcome("range-outcome", "range-candidate", "wins"),
        _outcome("legacy-outcome", "legacy-candidate", "wins"),
        _outcome("unmatched-outcome", "missing-candidate", "wins"),
    ])

    first = sync_strategy_family_result_journals(
        candidates_path=candidates,
        outcomes_path=outcomes,
        output_dir=tmp_path / "family-results",
    )
    trend_path = tmp_path / "family-results" / FAMILY_FILES["trend_breakout"]
    range_path = tmp_path / "family-results" / FAMILY_FILES["range_mean_reversion"]
    trend_rows, range_rows = _read(trend_path), _read(range_path)

    assert [row["event_type"] for row in trend_rows] == ["PAPER_CANDIDATE", "PAPER_OUTCOME"]
    assert [row["event_type"] for row in range_rows] == ["PAPER_CANDIDATE", "PAPER_OUTCOME"]
    assert {row["family_id"] for row in trend_rows} == {"trend_breakout"}
    assert {row["family_id"] for row in range_rows} == {"range_mean_reversion"}
    assert trend_rows[1]["outcome"] == "losses"
    assert range_rows[1]["outcome"] == "wins"
    assert len(trend_rows[1]["candidate_source_sha256"]) == 64
    assert len(range_rows[1]["source_record_sha256"]) == 64
    assert all(row["execution_enabled"] is False and row["orders_placed"] is False
               for row in trend_rows + range_rows)
    assert first["unattributed_candidate_count"] == 1
    assert first["unattributed_outcome_count"] == 1
    assert first["unmatched_outcome_count"] == 1
    assert first["families"]["trend_breakout"]["performance_eligible_resolved"] == 0
    assert first["families"]["range_mean_reversion"]["performance_eligible_resolved"] == 0

    second = sync_strategy_family_result_journals(
        candidates_path=candidates,
        outcomes_path=outcomes,
        output_dir=tmp_path / "family-results",
    )
    assert second["new_records_appended"] == {"trend_breakout": 0, "range_mean_reversion": 0}
    assert len(_read(trend_path)) == 2
    assert len(_read(range_path)) == 2


def test_family_journal_rejects_profile_version_mismatch(tmp_path):
    candidates = tmp_path / "candidates.jsonl"
    candidate = _candidate("trend-candidate", "UPTREND")
    candidate["gate_evidence"]["strategy_family_route"]["family_version"] = "unverified-version"
    _write(candidates, [candidate])
    _write(tmp_path / "outcomes.jsonl", [])

    with pytest.raises(ValueError, match="ROUTE_IDENTITY_MISMATCH"):
        sync_strategy_family_result_journals(
            candidates_path=candidates,
            outcomes_path=tmp_path / "outcomes.jsonl",
            output_dir=tmp_path / "family-results",
        )


def test_family_journal_rejects_non_paper_candidate_or_outcome(tmp_path):
    candidates = tmp_path / "candidates.jsonl"
    candidate = _candidate("trend-candidate", "UPTREND")
    candidate["execution_enabled"] = True
    _write(candidates, [candidate])
    _write(tmp_path / "outcomes.jsonl", [])

    with pytest.raises(ValueError, match="CANDIDATE_NOT_PAPER_ONLY"):
        sync_strategy_family_result_journals(
            candidates_path=candidates,
            outcomes_path=tmp_path / "outcomes.jsonl",
            output_dir=tmp_path / "family-results",
        )


def test_family_journal_rejects_mutated_canonical_source_event(tmp_path):
    candidates = tmp_path / "candidates.jsonl"
    outcomes = tmp_path / "outcomes.jsonl"
    candidate = _candidate("trend-candidate", "UPTREND")
    _write(candidates, [candidate])
    _write(outcomes, [_outcome("trend-outcome", "trend-candidate", "losses")])
    output = tmp_path / "family-results"
    sync_strategy_family_result_journals(
        candidates_path=candidates, outcomes_path=outcomes, output_dir=output
    )
    candidate["entry"] = 101.0
    _write(candidates, [candidate])
    with pytest.raises(ValueError, match="SOURCE_EVENT_MUTATED"):
        sync_strategy_family_result_journals(
            candidates_path=candidates, outcomes_path=outcomes, output_dir=output
        )


def test_family_journal_rejects_conflicting_top_level_and_route_family_identity(tmp_path):
    candidates = tmp_path / "candidates.jsonl"
    candidate = _candidate("trend-candidate", "UPTREND")
    candidate["strategy_family_id"] = "trend_breakout"
    candidate["gate_evidence"]["strategy_family_route"]["family_id"] = "range_mean_reversion"
    _write(candidates, [candidate])
    _write(tmp_path / "outcomes.jsonl", [])

    with pytest.raises(ValueError, match="ROUTE_IDENTITY_MISMATCH"):
        sync_strategy_family_result_journals(
            candidates_path=candidates,
            outcomes_path=tmp_path / "outcomes.jsonl",
            output_dir=tmp_path / "family-results",
        )
