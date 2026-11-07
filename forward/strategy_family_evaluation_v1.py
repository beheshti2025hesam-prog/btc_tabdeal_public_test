"""Family-isolated paper-performance acceptance coordinator.

Consumes independently produced, provenance-bound family reports. It does
not compute outcomes from raw trades or replace the canonical ledger reader;
its job is to prevent cross-family pooling and enforce the common acceptance
contract across each family and the combined daily signal ceiling.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from typing import Any, Mapping

from .strategy_family_router_v1 import RANGE_MEAN_REVERSION_RESEARCH_V1, TREND_BREAKOUT_V2

SCHEMA = "hes_strategy_family_evaluation_report_v1"
MINIMUM_RESOLVED_TRADES = 100
TARGET_WIN_RATE_PCT = 90.0
MAX_ACTIONABLE_SIGNALS_PER_UTC_DAY = 3
_PROFILES = {
    TREND_BREAKOUT_V2.family_id: TREND_BREAKOUT_V2,
    RANGE_MEAN_REVERSION_RESEARCH_V1.family_id: RANGE_MEAN_REVERSION_RESEARCH_V1,
}


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _digest(value: Mapping[str, Any], field: str) -> str:
    payload = {k: v for k, v in value.items() if k != field}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _validate_cost(cost: Any) -> bool:
    return (
        isinstance(cost, Mapping) and cost.get("status") == "VERIFIED"
        and cost.get("fees_slippage_verified") is True
        and _sha(cost.get("evidence_sha256"))
        and _finite(cost.get("fee_fraction_per_side")) and cost["fee_fraction_per_side"] >= 0
        and _finite(cost.get("slippage_fraction_per_side")) and cost["slippage_fraction_per_side"] >= 0
        and _sha(cost.get("model_sha256"))
        and _digest(cost, "model_sha256") == cost.get("model_sha256")
    )


def _validate_oos(oos: Any, family_id: str, family_version: str, cost: Mapping[str, Any]) -> list[str]:
    reasons = []
    if not isinstance(oos, Mapping) or oos.get("status") != "PASS":
        return ["INDEPENDENT_OOS_EVIDENCE_MISSING"]
    if oos.get("family_id") != family_id or oos.get("family_version") != family_version:
        reasons.append("INDEPENDENT_OOS_FAMILY_MISMATCH")
    count = oos.get("resolved_closed_trade_count")
    ow, ol, ob = oos.get("wins"), oos.get("losses"), oos.get("breakevens")
    if (type(count) is not int or count < MINIMUM_RESOLVED_TRADES
            or any(type(v) is not int or v < 0 for v in (ow, ol, ob))
            or count != ow + ol + ob):
        reasons.append("INDEPENDENT_OOS_SAMPLE_TOO_SMALL_OR_INVALID")
    rate = oos.get("win_rate_pct")
    expected_rate = round(100.0 * ow / count, 2) if type(count) is int and count > 0 and type(ow) is int else None
    if not _finite(rate) or rate <= TARGET_WIN_RATE_PCT or expected_rate is None or abs(float(rate) - expected_rate) > 0.01:
        reasons.append("INDEPENDENT_OOS_WIN_RATE_NOT_STRICTLY_ABOVE_90")
    if not _finite(oos.get("net_expectancy_after_costs")) or oos["net_expectancy_after_costs"] <= 0:
        reasons.append("INDEPENDENT_OOS_NET_EXPECTANCY_NOT_POSITIVE")
    if not _finite(oos.get("profit_factor_after_costs")) or oos["profit_factor_after_costs"] <= 1:
        reasons.append("INDEPENDENT_OOS_PROFIT_FACTOR_NOT_ABOVE_1")
    if not _finite(oos.get("maximum_drawdown")) or oos["maximum_drawdown"] < 0:
        reasons.append("INDEPENDENT_OOS_DRAWDOWN_INVALID")
    if not _sha(oos.get("evidence_sha256")) or not _sha(oos.get("report_sha256")):
        reasons.append("INDEPENDENT_OOS_PROVENANCE_MISSING")
    else:
        try:
            if _digest(oos, "report_sha256") != oos["report_sha256"]:
                reasons.append("INDEPENDENT_OOS_REPORT_HASH_MISMATCH")
        except (TypeError, ValueError):
            reasons.append("INDEPENDENT_OOS_REPORT_INVALID")
    oos_cost = oos.get("cost_model")
    if not _validate_cost(oos_cost) or oos_cost.get("evidence_sha256") != cost.get("evidence_sha256"):
        reasons.append("INDEPENDENT_OOS_COST_MODEL_MISMATCH")
    return reasons


def evaluate_family_acceptance(reports: Mapping[str, Any]) -> dict[str, Any]:
    """Require independent Trend and Range reports; never pool their outcomes.

    Each report must use cohort_family_ids=[family_id], a unique cohort_id,
    >=100 eligible resolved trades, strictly >90% wins, positive net
    expectancy, PF>1, a verified cost model, and independently hashed OOS
    evidence. Both families remain non-activating even when this evidence gate
    passes; activation and live execution require separate approvals.
    """
    if not isinstance(reports, Mapping):
        reports = {}
    families: dict[str, Any] = {}
    daily_totals: dict[str, int] = {}
    cohort_ids: set[str] = set()
    for family_id, profile in _PROFILES.items():
        report = reports.get(family_id)
        reasons: list[str] = []
        if not isinstance(report, Mapping):
            families[family_id] = {"status": "NOT_MET", "reason_codes": ["FAMILY_REPORT_MISSING"], "activation_authorized": False}
            continue
        if report.get("schema") != SCHEMA or report.get("family_id") != family_id or report.get("family_version") != profile.version:
            reasons.append("FAMILY_REPORT_ID_OR_VERSION_MISMATCH")
        if report.get("cohort_family_ids") != [family_id]:
            reasons.append("CROSS_FAMILY_COHORT_MIXING_FORBIDDEN")
        cohort_id = report.get("cohort_id")
        if not isinstance(cohort_id, str) or not cohort_id.strip() or cohort_id in cohort_ids:
            reasons.append("FAMILY_COHORT_ID_MISSING_OR_REUSED")
        else:
            cohort_ids.add(cohort_id)
        if report.get("risk_policy_status") != "PASS":
            reasons.append("INDEPENDENT_RISK_POLICY_ACCEPTANCE_MISSING")
        if report.get("execution_enabled") is not False or report.get("orders_placed") is not False:
            reasons.append("PAPER_ONLY_EXECUTION_BOUNDARY_VIOLATION")
        count = report.get("resolved_closed_trade_count")
        wins, losses, breakevens = report.get("wins"), report.get("losses"), report.get("breakevens")
        timeouts = report.get("timeouts")
        if (any(type(v) is not int or v < 0 for v in (count, wins, losses, breakevens, timeouts))
                or count != wins + losses + breakevens):
            reasons.append("RESOLVED_OUTCOME_COUNTS_INVALID")
        elif count < MINIMUM_RESOLVED_TRADES:
            reasons.append("MINIMUM_100_RESOLVED_TRADES_NOT_MET")
        rate = report.get("win_rate_pct")
        expected_rate = round(100.0 * wins / count, 2) if type(count) is int and count > 0 and type(wins) is int else None
        if not _finite(rate) or rate <= TARGET_WIN_RATE_PCT or expected_rate is None or abs(float(rate) - expected_rate) > 0.01:
            reasons.append("IN_SAMPLE_WIN_RATE_NOT_STRICTLY_ABOVE_90")
        if not _finite(report.get("net_expectancy_after_costs")) or report["net_expectancy_after_costs"] <= 0:
            reasons.append("NET_EXPECTANCY_AFTER_COSTS_NOT_POSITIVE")
        if not _finite(report.get("profit_factor_after_costs")) or report["profit_factor_after_costs"] <= 1:
            reasons.append("PROFIT_FACTOR_AFTER_COSTS_NOT_ABOVE_1")
        if not _finite(report.get("maximum_drawdown")) or report["maximum_drawdown"] < 0:
            reasons.append("MAXIMUM_DRAWDOWN_INVALID")
        cost = report.get("cost_model")
        if not _validate_cost(cost):
            reasons.append("VERIFIED_FEE_SLIPPAGE_MODEL_MISSING")
        reasons.extend(_validate_oos(report.get("independent_oos"), family_id, profile.version, cost if isinstance(cost, Mapping) else {}))
        daily = report.get("daily_actionable_signals_by_utc_day")
        if not isinstance(daily, Mapping):
            reasons.append("FAMILY_DAILY_SIGNAL_COUNTS_MISSING")
        else:
            for day, value in daily.items():
                try:
                    date.fromisoformat(day)
                except (TypeError, ValueError):
                    reasons.append("FAMILY_DAILY_SIGNAL_DATE_INVALID")
                    continue
                if type(value) is not int or value < 0:
                    reasons.append("FAMILY_DAILY_SIGNAL_COUNT_INVALID")
                    continue
                daily_totals[day] = daily_totals.get(day, 0) + value
        if not _sha(report.get("evidence_sha256")) or not _sha(report.get("report_sha256")):
            reasons.append("FAMILY_REPORT_PROVENANCE_MISSING")
        else:
            try:
                if _digest(report, "report_sha256") != report["report_sha256"]:
                    reasons.append("FAMILY_REPORT_HASH_MISMATCH")
            except (TypeError, ValueError):
                reasons.append("FAMILY_REPORT_INVALID")
        families[family_id] = {
            "status": "PASS" if not reasons else "NOT_MET",
            "reason_codes": list(dict.fromkeys(reasons)),
            "resolved_closed_trade_count": count if type(count) is int else None,
            "win_rate_pct": rate if _finite(rate) else None,
            "activation_state": profile.activation_state,
            "activation_authorized": False,
            "execution_enabled": False,
            "orders_placed": False,
        }

    cap_exceeded = any(value > MAX_ACTIONABLE_SIGNALS_PER_UTC_DAY for value in daily_totals.values())
    if cap_exceeded:
        for item in families.values():
            item["status"] = "NOT_MET"
            item["reason_codes"] = list(dict.fromkeys(item.get("reason_codes", []) + ["GLOBAL_DAILY_SIGNAL_CAP_EXCEEDED"]))
    all_present = set(reports.keys()) == set(_PROFILES.keys())
    overall_pass = all_present and all(item.get("status") == "PASS" for item in families.values()) and not cap_exceeded
    overall_reasons = []
    if not all_present:
        overall_reasons.append("BOTH_AND_ONLY_APPROVED_FAMILY_REPORTS_REQUIRED")
    if cap_exceeded:
        overall_reasons.append("GLOBAL_DAILY_SIGNAL_CAP_EXCEEDED")
    return {
        "schema": "hes_strategy_family_acceptance_result_v1",
        "status": "PASS" if overall_pass else "NOT_MET",
        "reason_codes": overall_reasons,
        "families": families,
        "daily_actionable_signals_by_utc_day_global": dict(sorted(daily_totals.items())),
        "max_actionable_signals_per_utc_day": MAX_ACTIONABLE_SIGNALS_PER_UTC_DAY,
        "daily_signal_limit_is_global_cap_not_quota": True,
        "minimum_resolved_trades_per_family": MINIMUM_RESOLVED_TRADES,
        "target_win_rate_operator": ">",
        "target_win_rate_pct": TARGET_WIN_RATE_PCT,
        "activation_authorized": False,
        "execution_enabled": False,
        "orders_placed": False,
    }
