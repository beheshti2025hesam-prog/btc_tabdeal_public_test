import json

import pytest

from forward.blackbox_experience_memory_v1 import collect_canonical_experiences


def test_mother_family_paper_events_keep_family_identity_and_never_become_training_labels(tmp_path):
    base = tmp_path / "data" / "forward"
    base.mkdir(parents=True)
    hashes = {
        "mother_snapshot_sha256": "a" * 64,
        "mother_audit_sha256": "b" * 64,
        "mother_trace_id": "c" * 64,
        "news_snapshot_sha256": "d" * 64,
        "news_brief_sha256": "e" * 64,
    }
    mother = {
        "schema": "hes_mother_decision_journal_event_v1", "event_id": "mother-1",
        "observed_at": "2026-11-22T15:00:00+00:00", "symbol": "BTC_USDT", "timeframe": "15m",
        "market_regime": "DOWNTREND", "decision": "NO_TRADE", "direction": "SHORT",
        "policy_version": "generic-policy-v1", "strategy_family_id": "trend_breakout",
        "source_hashes": hashes,
        "gate_evidence": {"news_context": {"status": "READY"},
                          "strategy_family_paper_lane": {"selected_candidate": {"event_id": "family-paper-1"}}},
    }
    candidate = {
        "schema": "hes_trade_journal_paper_candidate_v1", "event_id": "family-paper-1",
        "candidate_event_id": "family-paper-1", "observed_at": "2026-11-22T15:00:00+00:00",
        "symbol": "BTC_USDT", "timeframe": "15m", "direction": "SHORT", "decision": "PAPER_CANDIDATE",
        "final_gate_decision": "NO_TRADE", "strategy_family_id": "trend_breakout",
        "policy_version": "generic-policy-v1", "source_hashes": hashes,
    }
    outcome = {
        "schema": "hes_trade_journal_paper_outcome_v1", "event_id": "outcome-1",
        "candidate_event_id": "family-paper-1", "observed_at": "2026-11-22T15:15:00+00:00",
        "symbol": "BTC_USDT", "timeframe": "15m", "direction": "SHORT", "decision": "PAPER_OUTCOME",
        "final_gate_decision": "NO_TRADE", "strategy_family_id": "trend_breakout",
        "policy_version": "generic-policy-v1", "outcome": "wins", "source_hashes": hashes,
    }
    (base / "trade_journal_v2.jsonl").write_text("\n".join(json.dumps(x) for x in (mother, candidate, outcome)) + "\n")
    events, counts = collect_canonical_experiences(tmp_path)
    assert counts["trade_journal_v2.jsonl"] == 3
    by_source = {e["source_event_id"]: e for e in events}
    assert by_source["mother-1"]["family_id"] == "trend_breakout"
    assert by_source["mother-1"]["experience_type"] == "FAMILY_RESEARCH"
    assert by_source["mother-1"]["provenance_complete"] is True
    assert by_source["family-paper-1"]["family_id"] == "trend_breakout"
    assert by_source["family-paper-1"]["experience_type"] == "FAMILY_RESEARCH"
    assert by_source["outcome-1"]["family_id"] == "trend_breakout"
    assert by_source["outcome-1"]["experience_type"] == "TRADE_OUTCOME"
    assert by_source["outcome-1"]["outcome_class"] == "WIN"
    assert by_source["outcome-1"]["training_eligible"] is False


def _paper_outcome_pair(*, journal_outcome="losses", ledger_outcome="losses"):
    hashes = {
        "mother_snapshot_sha256": "a" * 64,
        "mother_audit_sha256": "b" * 64,
        "mother_trace_id": "c" * 64,
        "news_snapshot_sha256": "d" * 64,
        "news_brief_sha256": "e" * 64,
    }
    journal = {
        "schema": "hes_trade_journal_paper_outcome_v1",
        "event_id": "outcome-mirror-1",
        "candidate_event_id": "candidate-mirror-1",
        "observed_at": "2026-11-24T10:00:00+00:00",
        "symbol": "BTC_USDT", "timeframe": "15m", "direction": "SHORT",
        "decision": "PAPER_OUTCOME", "candidate_time": 1795509000,
        "entry": 90000.0, "stop_loss": 91000.0, "take_profit": 87000.0,
        "exit_time": 1795510800, "exit_close": 90500.0, "exit_price": 91000.0,
        "outcome_reason": "STOP_LOSS", "outcome": journal_outcome,
        "strategy_family_id": "range_mean_reversion", "source_hashes": hashes,
    }
    ledger = {
        "schema": "hes_strategy_policy_v2_paper_outcome",
        "event_id": "outcome-mirror-1",
        "candidate_event_id": "candidate-mirror-1",
        "resolved_at": "2026-11-24T10:00:00+00:00",
        "symbol": "BTC_USDT", "timeframe": "15m", "direction": "SHORT",
        "candidate_time": 1795509000, "entry": 90000.0,
        "stop_loss": 91000.0, "take_profit": 87000.0,
        "exit_close_time": 1795510800, "exit_close": 90500.0,
        "exit_price": 91000.0, "reason": "STOP_LOSS",
        "outcome": ledger_outcome, "final_gate_decision": "NO_TRADE",
        "strategy_family_id": "range_mean_reversion",
        "source_hashes": hashes, "run_manifest_sha256": "f" * 64,
        "costs_verified": True, "net_R": 1.25,
    }
    return journal, ledger


def test_mirrored_paper_outcome_is_indexed_once_from_richer_canonical_ledger(tmp_path):
    base = tmp_path / "data" / "forward"
    base.mkdir(parents=True)
    journal, ledger = _paper_outcome_pair()
    (base / "trade_journal_v2.jsonl").write_text(json.dumps(journal) + "\n")
    (base / "strategy_policy_v2_eval_outcomes.jsonl").write_text(json.dumps(ledger) + "\n")

    events, counts = collect_canonical_experiences(tmp_path)
    matches = [e for e in events if e["source_event_id"] == "outcome-mirror-1"
               and e["experience_type"] == "TRADE_OUTCOME"]

    assert len(matches) == 1
    assert matches[0]["source_ref"] == "data/forward/strategy_policy_v2_eval_outcomes.jsonl"
    assert matches[0]["provenance_complete"] is True
    assert matches[0]["costs_verified"] is True
    assert matches[0]["training_eligible"] is False
    assert counts["trade_journal_v2.jsonl"] == 0
    assert counts["strategy_policy_v2_eval_outcomes.jsonl"] == 1


def test_conflicting_paper_outcome_mirror_fails_closed(tmp_path):
    base = tmp_path / "data" / "forward"
    base.mkdir(parents=True)
    journal, ledger = _paper_outcome_pair(journal_outcome="losses", ledger_outcome="wins")
    (base / "trade_journal_v2.jsonl").write_text(json.dumps(journal) + "\n")
    (base / "strategy_policy_v2_eval_outcomes.jsonl").write_text(json.dumps(ledger) + "\n")

    with pytest.raises(ValueError, match="PAPER_OUTCOME_MIRROR_CONFLICT"):
        collect_canonical_experiences(tmp_path)
