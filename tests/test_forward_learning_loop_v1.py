import pytest
from forward.learning_loop_v1 import build_learning_report, report_json

def sample():
    return [{"event_id": f"e{i}", "decision": "LONG", "market_regime": "TREND", "decision_gate": "ENTRY", "outcome": "LOSS" if i < 5 else "WIN"} for i in range(1, 7)] + [{"event_id":"reject-1","decision":"NO_TRADE","rejected_at":"RISK","reason_codes":["RR_TOO_LOW"],"outcome":None}]

def test_reports_loss_concentration_as_hypothesis_only():
    r=build_learning_report(sample(), min_group_size=5)
    assert r.eligible_closed_trade_count == 6 and r.decision_counts["NO_TRADE"] == 1
    assert any(h["type"]=="INVESTIGATE_LOSS_CONCENTRATION" and h["action"]=="RESEARCH_ONLY_NO_PARAMETER_CHANGE" for h in r.hypotheses)

def test_open_trade_excluded_from_closed_count():
    r=build_learning_report(sample()+[{"event_id":"open-1","decision":"SHORT","outcome":"OPEN"}])
    assert r.eligible_closed_trade_count == 6 and r.excluded_unclosed_count == 1

def test_duplicate_events_fail_closed():
    with pytest.raises(ValueError, match="duplicate_event_id"):
        build_learning_report([{"event_id":"x","decision":"NO_TRADE"},{"event_id":"x","decision":"NO_TRADE"}])

def test_historical_winner_population_forbidden():
    with pytest.raises(ValueError, match="HISTORICAL_POPULATION_FORBIDDEN"):
        build_learning_report([{"event_id":"x","decision":"LONG","population":"Winner"}])

def test_no_trade_cannot_have_trade_outcome():
    with pytest.raises(ValueError, match="NO_TRADE_CANNOT_HAVE_TRADE_OUTCOME"):
        build_learning_report([{"event_id":"x","decision":"NO_TRADE","outcome":"WIN"}])

def test_report_serialization_deterministic():
    assert report_json(build_learning_report(sample())) == report_json(build_learning_report(sample()))
