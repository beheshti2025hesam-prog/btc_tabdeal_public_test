import hashlib
import json

from forward.strategy_family_evaluation_v1 import (
    SCHEMA,
    evaluate_family_acceptance,
)
from forward.strategy_family_router_v1 import RANGE_MEAN_REVERSION_RESEARCH_V1, TREND_BREAKOUT_V2


def digest(value, field):
    payload = {k: v for k, v in value.items() if k != field}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def cost_model():
    model = {
        "status": "VERIFIED", "fees_slippage_verified": True,
        "fee_fraction_per_side": 0.001, "slippage_fraction_per_side": 0.0005,
        "evidence_sha256": "a" * 64,
    }
    model["model_sha256"] = digest(model, "model_sha256")
    return model


def oos_report(family_id, version, cost):
    report = {
        "status": "PASS", "family_id": family_id, "family_version": version,
        "resolved_closed_trade_count": 100, "wins": 91, "losses": 9, "breakevens": 0,
        "win_rate_pct": 91.0, "net_expectancy_after_costs": 0.25,
        "profit_factor_after_costs": 2.0, "maximum_drawdown": 0.08,
        "cost_model": cost, "evidence_sha256": "b" * 64,
    }
    report["report_sha256"] = digest(report, "report_sha256")
    return report


def family_report(family_id, version, cohort_id, daily):
    cost = cost_model()
    report = {
        "schema": SCHEMA, "family_id": family_id, "family_version": version,
        "cohort_family_ids": [family_id], "cohort_id": cohort_id,
        "risk_policy_status": "PASS", "execution_enabled": False, "orders_placed": False,
        "resolved_closed_trade_count": 100, "wins": 91, "losses": 9, "breakevens": 0,
        "timeouts": 2, "win_rate_pct": 91.0, "net_expectancy_after_costs": 0.20,
        "profit_factor_after_costs": 1.8, "maximum_drawdown": 0.10,
        "cost_model": cost, "independent_oos": oos_report(family_id, version, cost),
        "daily_actionable_signals_by_utc_day": daily,
        "evidence_sha256": "c" * 64,
    }
    report["report_sha256"] = digest(report, "report_sha256")
    return report


def valid_reports():
    return {
        "trend_breakout": family_report("trend_breakout", TREND_BREAKOUT_V2.version, "trend-cohort-1", {"2026-11-01": 2}),
        "range_mean_reversion": family_report("range_mean_reversion", RANGE_MEAN_REVERSION_RESEARCH_V1.version, "range-cohort-1", {"2026-11-01": 1}),
    }


def test_each_family_requires_independent_cohort_and_independent_oos():
    result = evaluate_family_acceptance(valid_reports())
    assert result["status"] == "PASS"
    assert result["families"]["trend_breakout"]["status"] == "PASS"
    assert result["families"]["range_mean_reversion"]["status"] == "PASS"
    assert result["daily_actionable_signals_by_utc_day_global"] == {"2026-11-01": 3}
    assert result["activation_authorized"] is False
    assert result["execution_enabled"] is False and result["orders_placed"] is False


def test_missing_family_report_cannot_be_pooled_with_other_family():
    result = evaluate_family_acceptance({"trend_breakout": valid_reports()["trend_breakout"]})
    assert result["status"] == "NOT_MET"
    assert result["families"]["range_mean_reversion"]["reason_codes"] == ["FAMILY_REPORT_MISSING"]


def test_cross_family_cohort_is_rejected():
    reports = valid_reports()
    reports["range_mean_reversion"]["cohort_family_ids"] = ["trend_breakout", "range_mean_reversion"]
    reports["range_mean_reversion"]["report_sha256"] = digest(reports["range_mean_reversion"], "report_sha256")
    result = evaluate_family_acceptance(reports)
    assert result["status"] == "NOT_MET"
    assert "CROSS_FAMILY_COHORT_MIXING_FORBIDDEN" in result["families"]["range_mean_reversion"]["reason_codes"]


def test_daily_signal_limit_is_global_across_families_not_three_per_family():
    reports = valid_reports()
    reports["trend_breakout"]["daily_actionable_signals_by_utc_day"] = {"2026-11-01": 2}
    reports["range_mean_reversion"]["daily_actionable_signals_by_utc_day"] = {"2026-11-01": 2}
    for report in reports.values():
        report["report_sha256"] = digest(report, "report_sha256")
    result = evaluate_family_acceptance(reports)
    assert result["status"] == "NOT_MET"
    for family in result["families"].values():
        assert "GLOBAL_DAILY_SIGNAL_CAP_EXCEEDED" in family["reason_codes"]


def test_90_percent_exactly_does_not_pass():
    reports = valid_reports()
    reports["trend_breakout"]["wins"] = 90
    reports["trend_breakout"]["losses"] = 10
    reports["trend_breakout"]["win_rate_pct"] = 90.0
    reports["trend_breakout"]["report_sha256"] = digest(reports["trend_breakout"], "report_sha256")
    result = evaluate_family_acceptance(reports)
    assert result["status"] == "NOT_MET"
    assert "IN_SAMPLE_WIN_RATE_NOT_STRICTLY_ABOVE_90" in result["families"]["trend_breakout"]["reason_codes"]


def test_invalid_hash_or_unverified_cost_model_fails_closed():
    reports = valid_reports()
    reports["range_mean_reversion"]["cost_model"]["status"] = "ASSUMED"
    reports["range_mean_reversion"]["report_sha256"] = digest(reports["range_mean_reversion"], "report_sha256")
    result = evaluate_family_acceptance(reports)
    assert result["status"] == "NOT_MET"
    assert "VERIFIED_FEE_SLIPPAGE_MODEL_MISSING" in result["families"]["range_mean_reversion"]["reason_codes"]
