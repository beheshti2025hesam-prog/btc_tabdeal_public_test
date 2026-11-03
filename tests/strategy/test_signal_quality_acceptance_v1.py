from pathlib import Path
from forward.signal_quality_acceptance_v1 import daily_signal_counts, evaluate_acceptance, load_contract

ROOT = Path(__file__).resolve().parents[2]

def good_metrics(**overrides):
    result = {"preapproval_paper_resolved":100,"preapproval_paper_win_rate_pct":91.0,
              "preapproval_paper_unscorable_outcomes":0,"unmatched_outcome_records":0,
              "ambiguous_legacy_timestamp_matches":0,
              "cost_model":{"status":"VERIFIED","fees_slippage_verified":True}}
    result.update(overrides)
    return result

def good_oos(**overrides):
    result = {"status":"PASS","resolved_closed_trade_count":100,"win_rate_pct":91.0,"evidence_sha256":"a"*64}
    result.update(overrides)
    return result

def test_contract_is_versioned_and_preserves_strict_targets():
    contract,digest=load_contract(ROOT)
    assert contract["paper_performance_gate"]["win_rate_operator"]==">"
    assert contract["paper_performance_gate"]["win_rate_pct"]==90.0
    assert contract["paper_performance_gate"]["minimum_resolved_closed_trades"]==100
    assert contract["signal_constraints"]["max_actionable_signals_per_utc_day"]==3
    assert len(digest)==64

def test_exactly_90_percent_does_not_pass():
    result=evaluate_acceptance(root=ROOT,metrics=good_metrics(preapproval_paper_win_rate_pct=90.0),candidates=[],independent_oos=good_oos())
    assert result["status"]=="NOT_MET"
    assert "STRICT_WIN_RATE_GT_90_NOT_MET" in result["reasons"]

def test_sample_size_missing_oos_and_cost_model_fail_closed():
    result=evaluate_acceptance(root=ROOT,metrics=good_metrics(preapproval_paper_resolved=99,cost_model={"status":"ASSUMPTION_BASED"}),candidates=[],independent_oos=None)
    assert result["status"]=="NOT_MET"
    assert "MINIMUM_RESOLVED_TRADES_NOT_MET" in result["reasons"]
    assert "VERIFIED_FEE_SLIPPAGE_MODEL_MISSING" in result["reasons"]
    assert "INDEPENDENT_OUT_OF_SAMPLE_EVIDENCE_MISSING" in result["reasons"]

def test_daily_cap_counts_only_paper_eligible_candidates():
    rows=[{"candidate_event_id":str(i),"candidate_time":1793577600+i*60,
           "preapproval_paper_eligible":i<3,"final_gate_decision":"NO_TRADE"} for i in range(4)]
    counts=daily_signal_counts(rows,performance_cohort="PREAPPROVAL_PAPER_ELIGIBLE")
    assert counts["max_signals_in_any_utc_day"]==3
    assert counts["invalid_actionable_records"]==0

def test_fourth_paper_eligible_signal_fails_daily_cap():
    rows=[{"candidate_event_id":str(i),"candidate_time":1793577600+i*60,
           "preapproval_paper_eligible":True,"final_gate_decision":"NO_TRADE"} for i in range(4)]
    result=evaluate_acceptance(root=ROOT,metrics=good_metrics(),candidates=rows,independent_oos=good_oos())
    assert result["status"]=="NOT_MET"
    assert "DAILY_SIGNAL_CAP_EXCEEDED" in result["reasons"]

def test_pass_requires_all_contract_gates():
    result=evaluate_acceptance(root=ROOT,metrics=good_metrics(),candidates=[],independent_oos=good_oos())
    assert result["status"]=="PASS"
    assert result["target_met_on_in_sample_metrics"] is True
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False
