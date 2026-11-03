"""Fail-closed evaluator for the versioned HES signal-quality acceptance contract."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

CONTRACT_RELATIVE_PATH = Path("docs/execution/SIGNAL_QUALITY_ACCEPTANCE_CONTRACT_V1.json")

def load_contract(root: str | Path) -> tuple[dict, str]:
    path = Path(root) / CONTRACT_RELATIVE_PATH
    raw = path.read_bytes()
    contract = json.loads(raw.decode("utf-8"))
    if contract.get("schema") != "hes_signal_quality_acceptance_v1" or contract.get("version") != "1.0.0":
        raise ValueError("unsupported signal-quality contract")
    gate = contract.get("paper_performance_gate", {})
    constraints = contract.get("signal_constraints", {})
    if gate.get("win_rate_operator") != ">" or float(gate.get("win_rate_pct", -1)) != 90.0:
        raise ValueError("contract must preserve strict >90% win-rate rule")
    if int(gate.get("minimum_resolved_closed_trades", 0)) != 100:
        raise ValueError("contract must preserve 100-trade minimum")
    if int(constraints.get("max_actionable_signals_per_utc_day", 0)) != 3:
        raise ValueError("contract must preserve three-signals-per-day cap")
    if constraints.get("no_signal_quota") is not True or constraints.get("no_trade_is_valid_output") is not True:
        raise ValueError("contract must preserve no-quota / NO_TRADE semantics")
    if gate.get("performance_cohort") not in ("PREAPPROVAL_PAPER_ELIGIBLE", "GATE_APPROVED_ONLY", "PRECISION_ENTRY_PAPER_ELIGIBLE"):
        raise ValueError("unsupported paper performance cohort")
    return contract, hashlib.sha256(raw).hexdigest()

def _utc_day(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        stamp = float(value)
        if stamp > 100_000_000_000:
            stamp /= 1000.0
        return datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("empty candidate timestamp")
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid candidate timestamp") from exc
        if dt.tzinfo is None:
            raise ValueError("naive candidate timestamp is not allowed")
        return dt.astimezone(timezone.utc).date().isoformat()
    raise ValueError("candidate timestamp missing or unsupported")

def daily_signal_counts(candidates: list[dict], *, performance_cohort: str) -> dict:
    """Count only candidates admitted to the contract paper cohort; never impose a quota."""
    counts: dict[str, int] = {}
    seen: set[str] = set()
    invalid = 0
    for row in candidates:
        if performance_cohort == "PREAPPROVAL_PAPER_ELIGIBLE":
            actionable = row.get("preapproval_paper_eligible") is True
        elif performance_cohort == "PRECISION_ENTRY_PAPER_ELIGIBLE":
            actionable = row.get("schema") == "hes_precision_entry_paper_candidate_v1" and row.get("paper_only") is True and row.get("preapproval_paper_eligible") is True
        elif performance_cohort == "GATE_APPROVED_ONLY":
            actionable = row.get("final_gate_decision") in ("LONG", "SHORT")
        else:
            raise ValueError("unsupported performance cohort")
        if not actionable:
            continue
        event_id = row.get("candidate_event_id") or row.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip() or event_id in seen:
            invalid += 1
            continue
        seen.add(event_id)
        try:
            day = _utc_day(row.get("candidate_time", row.get("observed_at")))
        except (TypeError, ValueError, OverflowError, OSError):
            invalid += 1
            continue
        counts[day] = counts.get(day, 0) + 1
    return {"counts_by_utc_day": dict(sorted(counts.items())), "max_signals_in_any_utc_day": max(counts.values(), default=0), "invalid_actionable_records": invalid}

def evaluate_acceptance(*, root: str | Path, metrics: dict, candidates: list[dict], independent_oos: dict | None = None) -> dict:
    """Evaluate claims conservatively. Missing OOS/cost evidence is a hard blocker."""
    contract, digest = load_contract(root)
    gate = contract["paper_performance_gate"]
    cap = contract["signal_constraints"]["max_actionable_signals_per_utc_day"]
    minimum = int(gate["minimum_resolved_closed_trades"])
    target = float(gate["win_rate_pct"])
    cohort = gate.get("performance_cohort", "GATE_APPROVED_ONLY")
    reasons = []
    unresolved_candidates = 0
    if cohort == "PRECISION_ENTRY_PAPER_ELIGIBLE":
        resolved = int(metrics.get("precision_paper_resolved", metrics.get("resolved", 0)) or 0)
        win_rate = metrics.get("precision_paper_win_rate_pct", metrics.get("win_rate_pct"))
        unscorable = int(metrics.get("precision_paper_unscorable_outcomes", metrics.get("unscorable_outcomes", 0)) or 0)
        unresolved_candidates = int(metrics.get("precision_paper_unresolved_candidates", 0) or 0)
    elif cohort == "PREAPPROVAL_PAPER_ELIGIBLE":
        resolved = int(metrics.get("preapproval_paper_resolved", metrics.get("resolved", 0)) or 0)
        win_rate = metrics.get("preapproval_paper_win_rate_pct", metrics.get("win_rate_pct"))
        unscorable = int(metrics.get("preapproval_paper_unscorable_outcomes", metrics.get("unscorable_outcomes", 0)) or 0)
    elif cohort == "GATE_APPROVED_ONLY":
        resolved = int(metrics.get("eligible_resolved", metrics.get("resolved", 0)) or 0)
        win_rate = metrics.get("eligible_win_rate_pct", metrics.get("win_rate_pct"))
        unscorable = int(metrics.get("eligible_unscorable_outcomes", metrics.get("unscorable_outcomes", 0)) or 0)
    else:
        raise ValueError("unsupported performance cohort in acceptance contract")
    if resolved < minimum:
        reasons.append("MINIMUM_RESOLVED_TRADES_NOT_MET")
    if win_rate is None or float(win_rate) <= target:
        reasons.append("STRICT_WIN_RATE_GT_90_NOT_MET")
    unmatched = int(metrics.get("unmatched_outcome_records", metrics.get("unmatched_outcomes", 0)) or 0)
    ambiguous = int(metrics.get("ambiguous_legacy_timestamp_matches", metrics.get("ambiguous_outcomes", 0)) or 0)
    if unmatched: reasons.append("UNMATCHED_OUTCOMES_PRESENT")
    if ambiguous: reasons.append("AMBIGUOUS_OUTCOME_LINKS_PRESENT")
    if unscorable: reasons.append("UNSCORABLE_OUTCOMES_PRESENT")
    if unresolved_candidates: reasons.append("UNRESOLVED_PRECISION_CANDIDATES_PRESENT")
    daily = daily_signal_counts(candidates, performance_cohort=cohort)
    if daily["invalid_actionable_records"]: reasons.append("INVALID_ACTIONABLE_SIGNAL_RECORDS")
    if daily["max_signals_in_any_utc_day"] > cap: reasons.append("DAILY_SIGNAL_CAP_EXCEEDED")
    cost = metrics.get("cost_model", {})
    if cost.get("status") != "VERIFIED" or cost.get("fees_slippage_verified") is not True:
        reasons.append("VERIFIED_FEE_SLIPPAGE_MODEL_MISSING")
    if not isinstance(independent_oos, dict) or independent_oos.get("status") != "PASS":
        reasons.append("INDEPENDENT_OUT_OF_SAMPLE_EVIDENCE_MISSING")
    else:
        if int(independent_oos.get("resolved_closed_trade_count", 0) or 0) < minimum:
            reasons.append("INDEPENDENT_OOS_SAMPLE_TOO_SMALL")
        oos_wr = independent_oos.get("win_rate_pct")
        if oos_wr is None or float(oos_wr) <= target:
            reasons.append("INDEPENDENT_OOS_WIN_RATE_NOT_ABOVE_90")
        if not independent_oos.get("evidence_sha256"):
            reasons.append("INDEPENDENT_OOS_PROVENANCE_MISSING")
    return {
        "schema": "hes_signal_quality_acceptance_result_v1",
        "contract_version": contract["version"],
        "contract_sha256": digest,
        "performance_cohort": cohort,
        "status": "PASS" if not reasons else "NOT_MET",
        "target_win_rate_operator": ">",
        "target_win_rate_pct": target,
        "minimum_resolved_closed_trades": minimum,
        "resolved_closed_trade_count": resolved,
        "observed_win_rate_pct": win_rate,
        "target_met_on_in_sample_metrics": bool(resolved >= minimum and win_rate is not None and float(win_rate) > target and not unmatched and not ambiguous and not unscorable),
        "daily_signal_cap": cap,
        "daily_signal_counts": daily,
        "unmatched_outcome_records": unmatched,
        "ambiguous_outcome_links": ambiguous,
        "unscorable_outcomes": unscorable,
        "unresolved_precision_candidates": unresolved_candidates,
        "independent_oos_status": independent_oos.get("status") if isinstance(independent_oos, dict) else "MISSING",
        "cost_model_status": cost.get("status", "MISSING"),
        "reasons": reasons,
        "execution_enabled": False,
        "orders_placed": False,
    }
