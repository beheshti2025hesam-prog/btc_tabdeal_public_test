import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_strategy_policy_v2_forward_eval.py"
spec = importlib.util.spec_from_file_location("paper_evaluator_linkage", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_stable_candidate_ids_prevent_same_timestamp_cross_linking(tmp_path, monkeypatch):
    data = tmp_path / "forward"
    data.mkdir()
    candidates = [
        {"candidate_event_id": "candidate-A", "candidate_time": 100, "symbol": "BTC_USDT",
         "direction": "LONG", "entry": 100, "stop_loss": 99, "take_profit": 103,
         "final_gate_decision": "LONG"},
        {"candidate_event_id": "candidate-B", "candidate_time": 100, "symbol": "BTC_USDT",
         "direction": "SHORT", "entry": 100, "stop_loss": 101, "take_profit": 97,
         "final_gate_decision": "NO_TRADE"},
    ]
    outcomes = [
        {"candidate_event_id": "candidate-A", "candidate_time": 100, "direction": "LONG",
         "entry": 100, "stop_loss": 99, "take_profit": 103, "outcome": "timeouts",
         "exit_price": 101, "exit_close": 101, "reason": "MAX_HOLD_24H"},
        {"candidate_event_id": "candidate-B", "candidate_time": 100, "direction": "SHORT",
         "entry": 100, "stop_loss": 101, "take_profit": 97, "outcome": "losses",
         "exit_price": 101, "exit_close": 101, "reason": "STOP_LOSS"},
        {"candidate_time": 100, "direction": "LONG", "entry": 100, "stop_loss": 99,
         "take_profit": 103, "outcome": "wins", "exit_close": 103, "reason": "TAKE_PROFIT"},
    ]
    cpath, opath = data / "candidates.jsonl", data / "outcomes.jsonl"
    cpath.write_text("".join(json.dumps(x) + "\n" for x in candidates))
    opath.write_text("".join(json.dumps(x) + "\n" for x in outcomes))
    monkeypatch.setattr(mod, "CAND", cpath)
    monkeypatch.setattr(mod, "OUT", opath)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    cfg = tmp_path / "forward"
    cfg.mkdir(exist_ok=True)
    (cfg / "paper_risk_context_v1.json").write_text(json.dumps({
        "fee_fraction_per_side": 0.001, "slippage_fraction_per_side": 0.0005
    }))

    result = mod.performance_metrics()
    assert result["candidate_records"] == 2
    assert result["linked_outcome_records"] == 2
    assert result["unmatched_outcome_records"] == 1
    assert result["ambiguous_legacy_timestamp_matches"] == 1
    assert result["eligible_resolved"] == 1
    assert result["eligible_wins"] == 1
    assert result["eligible_timeouts"] == 1
    assert result["eligible_win_rate_pct"] == 100.0
    assert result["excluded_rejected_outcomes"] == 1


def test_legacy_timestamp_fallback_requires_unique_candidate(tmp_path, monkeypatch):
    data = tmp_path / "forward"
    data.mkdir()
    cpath, opath = data / "candidates.jsonl", data / "outcomes.jsonl"
    cpath.write_text(json.dumps({
        "candidate_time": 100, "direction": "LONG", "entry": 100, "stop_loss": 99,
        "take_profit": 103, "final_gate_decision": "LONG"
    }) + "\n")
    opath.write_text(json.dumps({
        "candidate_time": 100, "direction": "LONG", "entry": 100, "stop_loss": 99,
        "take_profit": 103, "outcome": "wins", "exit_close": 103, "reason": "TAKE_PROFIT"
    }) + "\n")
    monkeypatch.setattr(mod, "CAND", cpath)
    monkeypatch.setattr(mod, "OUT", opath)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    (data / "paper_risk_context_v1.json").write_text(json.dumps({
        "fee_fraction_per_side": 0.001, "slippage_fraction_per_side": 0.0005
    }))
    result = mod.performance_metrics()
    assert result["linked_outcome_records"] == 1
    assert result["unmatched_outcome_records"] == 0
    assert result["eligible_resolved"] == 1


def test_win_rate_target_requires_sample_size_and_clean_linkage():
    metrics = {
        "eligible_resolved": 30, "eligible_win_rate_pct": 90.0,
        "unmatched_outcome_records": 0, "ambiguous_legacy_timestamp_matches": 0,
        "eligible_unscorable_outcomes": 0,
    }
    assert mod.win_rate_target_met(metrics, minimum_resolved=30, target_pct=90.0) is False
    assert mod.win_rate_target_met({**metrics, "eligible_win_rate_pct":90.01}, minimum_resolved=30, target_pct=90.0) is True
    assert mod.win_rate_target_met({**metrics, "eligible_resolved": 29}, minimum_resolved=30, target_pct=90.0) is False
    assert mod.win_rate_target_met({**metrics, "unmatched_outcome_records": 1}, minimum_resolved=30, target_pct=90.0) is False
    assert mod.win_rate_target_met({**metrics, "eligible_unscorable_outcomes": 1}, minimum_resolved=30, target_pct=90.0) is False


def test_preapproval_paper_eligibility_is_separate_from_final_gate():
    from types import SimpleNamespace
    proposal = SimpleNamespace(decision="LONG", direction="LONG", entry=100.0,
                               stop_loss=99.0, take_profit=103.0, rr=3.0)
    evidence = {
        "structure": {"status":"OBSERVED", "regime":"UPTREND"},
        "confirmation": {"state":"CONFIRMED_LONG"},
        "risk": {"state":"RISK_APPROVED"},
        "execution_enabled": False, "orders_placed": False,
    }
    result = mod.preapproval_paper_eligibility(proposal, evidence)
    assert result["eligible"] is True
    assert result["status"] == "PREAPPROVAL_PAPER_ELIGIBLE"
    assert result["final_gate_approval_required"] is True
    assert result["execution_enabled"] is False and result["orders_placed"] is False

    blocked = mod.preapproval_paper_eligibility(proposal, {**evidence, "risk":{"state":"RISK_REJECTED"}})
    assert blocked["eligible"] is False
    assert "RISK_NOT_APPROVED" in blocked["reasons"]


def test_preapproval_paper_outcomes_are_scored_separately_from_official_approved_trades(tmp_path, monkeypatch):
    data = tmp_path / "forward"
    data.mkdir()
    candidate = {
        "candidate_event_id":"candidate-paper-only", "event_id":"candidate-paper-only",
        "candidate_time":100, "symbol":"BTC_USDT", "direction":"LONG",
        "entry":100, "stop_loss":99, "take_profit":103, "final_gate_decision":"NO_TRADE",
        "preapproval_paper_eligible":True,
    }
    outcome = {
        "candidate_event_id":"candidate-paper-only", "candidate_time":100, "direction":"LONG",
        "entry":100, "stop_loss":99, "take_profit":103, "outcome":"wins",
        "exit_price":103, "exit_close":103, "reason":"TAKE_PROFIT",
    }
    cpath, opath = data/"candidates.jsonl", data/"outcomes.jsonl"
    cpath.write_text(json.dumps(candidate)+"\n")
    opath.write_text(json.dumps(outcome)+"\n")
    monkeypatch.setattr(mod,"CAND",cpath); monkeypatch.setattr(mod,"OUT",opath)
    monkeypatch.setattr(mod,"ROOT",tmp_path)
    (data/"paper_risk_context_v1.json").write_text(json.dumps({
        "fee_fraction_per_side":0.001, "slippage_fraction_per_side":0.0005
    }))
    result=mod.performance_metrics()
    assert result["eligible_resolved"] == 0
    assert result["eligible_win_rate_pct"] is None
    assert result["preapproval_paper_outcomes"] == 1
    assert result["preapproval_paper_resolved"] == 1
    assert result["preapproval_paper_wins"] == 1
    assert result["preapproval_paper_win_rate_pct"] == 100.0
    assert result["unmatched_outcome_records"] == 0


def test_preapproval_win_rate_target_also_requires_30_clean_resolved_outcomes():
    metrics = {
        "preapproval_paper_resolved": 30, "preapproval_paper_win_rate_pct": 90.0,
        "preapproval_paper_unscorable_outcomes": 0,
        "unmatched_outcome_records": 0, "ambiguous_legacy_timestamp_matches": 0,
    }
    assert mod.win_rate_target_met(metrics, cohort="preapproval_paper", minimum_resolved=30, target_pct=90.0) is False
    assert mod.win_rate_target_met({**metrics,"preapproval_paper_win_rate_pct":90.01}, cohort="preapproval_paper", minimum_resolved=30, target_pct=90.0) is True
    assert mod.win_rate_target_met({**metrics,"preapproval_paper_resolved":29},cohort="preapproval_paper",minimum_resolved=30,target_pct=90.0) is False
    assert mod.win_rate_target_met({**metrics,"unmatched_outcome_records":1},cohort="preapproval_paper",minimum_resolved=30,target_pct=90.0) is False
