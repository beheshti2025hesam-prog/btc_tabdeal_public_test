import json
from scripts.run_indicator_strategy_learning_v1 import build_report

def test_learning_bridge_links_shadow_journal_and_outcomes(tmp_path):
    journal=tmp_path/"journal.jsonl"; outcomes=tmp_path/"outcomes.jsonl"; report=tmp_path/"report.json"
    decision={"event_id":"candidate-1","strategy_family_id":"indicator_strategy","strategy_variant_id":"trend_confirmation",
        "market_regime":"BULLISH","research_only":True,"decision":"LONG"}
    outcome={"event_id":"outcome-1","candidate_event_id":"candidate-1","strategy_variant_id":"trend_confirmation",
        "market_regime":"BULLISH","outcome":"TAKE_PROFIT","research_only":True,"research_label_eligible":True,"training_label_eligible":False,
        "net_return_pct_by_cost_bps":{"20":0.5}}
    journal.write_text(json.dumps(decision)+"\n"); outcomes.write_text(json.dumps(outcome)+"\n")
    result=build_report(journal,outcomes,report)
    assert result["decision_records"]==1 and result["outcome_records"]==1
    assert result["variants"]["trend_confirmation"]["resolved"]==1
    assert result["training_gate"]["status"]=="TRAINING_BLOCKED_NO_ELIGIBLE_FORWARD_PAPER_LABELS"
    assert report.exists()

def test_learning_bridge_rejects_unmatched_and_ineligible_labels(tmp_path):
    journal=tmp_path/"journal.jsonl"; outcomes=tmp_path/"outcomes.jsonl"; report=tmp_path/"report.json"
    journal.write_text(json.dumps({"event_id":"candidate-1","strategy_family_id":"other","research_only":True})+"\n")
    outcomes.write_text("\n".join([
        json.dumps({"event_id":"outcome-1","candidate_event_id":"missing","training_label_eligible":True,"net_return_pct_by_cost_bps":{"20":1}}),
        json.dumps({"event_id":"outcome-2","candidate_event_id":"candidate-1","training_label_eligible":True,"net_return_pct_by_cost_bps":{"20":1}})
    ])+"\n")
    result=build_report(journal,outcomes,report)
    assert result["unmatched_outcomes"]==1
    assert result["ineligible_records"]==1
    assert result["variants"]=={}
    assert result["safety"]["policy_mutation_enabled"] is False
