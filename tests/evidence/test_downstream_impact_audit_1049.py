import json
from pathlib import Path

AUDIT = Path("evidence/downstream_impact_audit_1049_v1.json")

def test_downstream_impact_audit_invariants():
    d = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert d["status"] == "DOWNSTREAM_IMPACT_AUDITED"
    assert d["locked_evidence"]["evaluated_observations"] == 1049
    assert d["locked_evidence"]["fold_evaluated"] == [120,132,135,137,138,127,126,134]
    assert sum(d["locked_evidence"]["fold_evaluated"]) == 1049
    assert d["gap_boundary"]["affected_fold"] == 7
    assert d["gap_boundary"]["excluded_evaluator_observations"] == 0
    assert d["gap_boundary"]["observation_coverage_delta_pct"] == 0.0
    assert d["downstream_oos_impact"]["population_change_due_to_gap"] == 0
    assert d["downstream_oos_impact"]["fold7_evaluated_before_after"] == [134,134]
    assert d["fold_level_gross"]["gross_positive_folds"] == 5
    assert d["cost_slippage_impact"]["scenarios"][1]["total_adverse_bps"] == 14
    assert d["cost_slippage_impact"]["scenarios"][1]["wins"] == 14
    assert d["cost_slippage_impact"]["scenarios"][1]["losses"] == 1035
    assert d["cost_slippage_impact"]["positive_trade_survival_at_14bps_pct"] == 14/1049*100
    assert d["cost_slippage_impact"]["fold_survival_under_14bps"]["positive_folds"] == 0
    assert d["safety"]["locked_1049_modified"] is False
    assert d["safety"]["synthetic_fill"] is False
    assert d["safety"]["replacement_rows"] is False
    assert d["safety"]["causal_reassignment"] is False
