"""Fail-closed evaluator for the versioned HES signal-quality acceptance contract."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

CONTRACT_RELATIVE_PATH = Path("docs/execution/SIGNAL_QUALITY_ACCEPTANCE_CONTRACT_V1.json")
PRECISION_CANDIDATES = Path("data/forward/precision_entry_candidates_v1.jsonl")
PRECISION_OUTCOMES = Path("data/forward/precision_entry_outcomes_v1.jsonl")
PRECISION_COST_MODEL = Path("data/forward/precision_entry_cost_model_v1.json")
PRECISION_OOS = Path("data/forward/precision_entry_independent_oos_evidence_v1.json")


def _finite_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _valid_sha256(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value.lower())
    )


def _read_jsonl(path: Path):
    if not path.exists():
        return None, []
    raw = path.read_bytes()
    rows = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"blank precision ledger row:{path.name}:{number}")
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"precision ledger row is not an object:{path.name}:{number}")
        rows.append(row)
    return hashlib.sha256(raw).hexdigest(), rows


def _read_json(path: Path):
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def load_contract(root: str | Path) -> tuple[dict, str]:
    path = Path(root) / CONTRACT_RELATIVE_PATH
    raw = path.read_bytes()
    contract = json.loads(raw.decode("utf-8"))
    if contract.get("schema") != "hes_signal_quality_acceptance_v1":
        raise ValueError("unsupported signal-quality contract schema")
    if contract.get("version") != "1.0.0":
        raise ValueError("unsupported signal-quality contract version")
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
    if gate.get("performance_cohort") not in (
        "PRECISION_ENTRY_PAPER_ELIGIBLE",
        "PREAPPROVAL_PAPER_ELIGIBLE",
        "GATE_APPROVED_ONLY",
    ):
        raise ValueError("unsupported performance cohort")
    if (
        gate.get("exclude_unresolved_and_ambiguous_from_win_rate") is not True
        or gate.get("require_independent_out_of_sample_evidence") is not True
        or gate.get("no_historical_reselection_or_threshold_tuning_to_pass_gate") is not True
    ):
        raise ValueError("contract evidence / anti-overfit invariants are unsafe")
    expected_artifacts = {
        "candidates": str(PRECISION_CANDIDATES),
        "outcomes": str(PRECISION_OUTCOMES),
        "verified_cost_model": str(PRECISION_COST_MODEL),
        "independent_out_of_sample": str(PRECISION_OOS),
    }
    if contract.get("precision_artifacts") != expected_artifacts:
        raise ValueError("precision artifact paths do not match the acceptance reader")
    activation = contract.get("activation", {})
    execution = contract.get("execution_boundary", {})
    if (
        activation.get("all_performance_and_safety_gates_required") is not True
        or activation.get("explicit_user_authorization_required") is not True
        or activation.get("until_then") != "PAPER_ONLY"
        or execution.get("live_execution_enabled") is not False
        or execution.get("orders_placed") is not False
    ):
        raise ValueError("contract activation / execution boundary is unsafe")
    return contract, hashlib.sha256(raw).hexdigest()


def _utc_day(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        stamp = float(value)
        if not math.isfinite(stamp):
            raise ValueError("non-finite candidate timestamp")
        if stamp > 100_000_000_000:  # milliseconds
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


def _precision_candidate_valid(row: dict) -> bool:
    if (
        row.get("schema") != "hes_precision_entry_paper_candidate_v1"
        or row.get("timeframe") != "1m"
        or row.get("source") != "gateio_public_spot"
        or row.get("symbol") != "BTC_USDT"
        or row.get("direction") not in ("LONG", "SHORT")
        or row.get("paper_only") is not True
        or row.get("preapproval_paper_eligible") is not True
        or row.get("execution_enabled") is not False
        or row.get("orders_placed") is not False
    ):
        return False
    event_id = row.get("candidate_event_id")
    if not isinstance(event_id, str) or not event_id.strip() or row.get("event_id") != event_id:
        return False
    if not isinstance(row.get("setup_id"), str) or not row["setup_id"].strip():
        return False
    if not _valid_sha256(row.get("setup_context_sha256")):
        return False
    entry_time = row.get("entry_time")
    if type(entry_time) is not int or entry_time <= 0:
        return False
    entry, stop, target = row.get("entry_price"), row.get("stop_price"), row.get("target_price")
    if not all(_finite_number(value) and value > 0 for value in (entry, stop, target)):
        return False
    if row["direction"] == "LONG":
        if not stop < entry < target:
            return False
    elif not target < entry < stop:
        return False
    risk = abs(entry - stop)
    return risk > 0 and abs(target - entry) / risk >= 3.0


def _precision_ledger_metrics(root: str | Path) -> dict:
    base = Path(root)
    candidate_hash, raw_candidates = _read_jsonl(base / PRECISION_CANDIDATES)
    outcome_hash, raw_outcomes = _read_jsonl(base / PRECISION_OUTCOMES)
    missing_ledger = candidate_hash is None or outcome_hash is None

    candidates = []
    candidate_by_id = {}
    seen_setup_ids = set()
    invalid_candidates = 0
    duplicate_candidate_ids = 0
    duplicate_setup_ids = 0
    for row in raw_candidates:
        if not _precision_candidate_valid(row):
            invalid_candidates += 1
            continue
        candidate_id = row["candidate_event_id"]
        if candidate_id in candidate_by_id:
            duplicate_candidate_ids += 1
            continue
        if row["setup_id"] in seen_setup_ids:
            duplicate_setup_ids += 1
            continue
        seen_setup_ids.add(row["setup_id"])
        candidate_by_id[candidate_id] = row
        candidates.append(row)

    wins = losses = timeouts = unmatched = ambiguous = unscorable = 0
    seen_outcome_ids = set()
    seen_candidate_outcomes = set()
    for row in raw_outcomes:
        event_id = row.get("event_id")
        candidate_id = row.get("candidate_event_id")
        if not isinstance(event_id, str) or not event_id.strip() or event_id in seen_outcome_ids:
            unscorable += 1
            continue
        seen_outcome_ids.add(event_id)
        candidate = candidate_by_id.get(candidate_id) if isinstance(candidate_id, str) else None
        if candidate is None:
            unmatched += 1
            continue
        if candidate_id in seen_candidate_outcomes:
            ambiguous += 1
            continue
        seen_candidate_outcomes.add(candidate_id)
        if (
            row.get("schema") != "hes_precision_entry_paper_outcome_v1"
            or row.get("setup_id") != candidate.get("setup_id")
            or row.get("source") != "gateio_public_spot"
            or row.get("symbol") != "BTC_USDT"
            or row.get("timeframe") != "1m"
            or row.get("direction") != candidate.get("direction")
            or row.get("entry_time") != candidate.get("entry_time")
            or not _valid_sha256(row.get("evidence_sha256"))
            or row.get("execution_enabled") is not False
            or row.get("orders_placed") is not False
            or not _finite_number(row.get("entry_price"))
            or not _finite_number(row.get("exit_price"))
            or row.get("entry_price") != candidate.get("entry_price")
            or row.get("outcome") not in ("WIN", "LOSS", "TIMEOUT")
            or not _finite_number(row.get("gross_r"))
            or type(row.get("exit_close_time")) is not int
            or row.get("exit_close_time", 0) <= candidate.get("entry_time", 0)
        ):
            unscorable += 1
            continue
        risk = abs(candidate["entry_price"] - candidate["stop_price"])
        expected_gross_r = (
            (row["exit_price"] - candidate["entry_price"]) / risk
            if candidate["direction"] == "LONG"
            else (candidate["entry_price"] - row["exit_price"]) / risk
        )
        if abs(expected_gross_r - row["gross_r"]) > 1e-6:
            unscorable += 1
            continue
        if row["outcome"] == "WIN":
            if row["gross_r"] <= 0:
                unscorable += 1
                continue
            wins += 1
        elif row["outcome"] == "LOSS":
            if row["gross_r"] >= 0:
                unscorable += 1
                continue
            losses += 1
        else:
            timeouts += 1

    resolved = wins + losses
    win_rate = round(100.0 * wins / resolved, 2) if resolved else None
    cost_model = _read_json(base / PRECISION_COST_MODEL) or {}
    independent_oos = _read_json(base / PRECISION_OOS)
    return {
        "candidate_rows": candidates,
        "candidate_count": len(raw_candidates),
        "valid_candidate_count": len(candidates),
        "outcome_count": len(raw_outcomes),
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "resolved": resolved,
        "win_rate_pct": win_rate,
        "unresolved_candidates": max(0, len(candidates) - len(seen_candidate_outcomes)),
        "invalid_candidate_records": invalid_candidates,
        "duplicate_candidate_ids": duplicate_candidate_ids,
        "duplicate_setup_ids": duplicate_setup_ids,
        "unmatched_outcome_records": unmatched,
        "ambiguous_outcome_links": ambiguous,
        "unscorable_outcomes": unscorable,
        "ledger_missing": missing_ledger,
        "cost_model": cost_model,
        "independent_oos": independent_oos,
        "source_sha256": {
            "candidates": candidate_hash,
            "outcomes": outcome_hash,
        },
    }


def _oos_report_completeness_reasons(report: dict, cost_model: dict) -> list[str]:
    reasons = []
    window = report.get("evaluation_window_utc")
    if not isinstance(window, dict):
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    else:
        try:
            start = datetime.fromisoformat(str(window["start"]).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(window["end"]).replace("Z", "+00:00"))
            if start.tzinfo is None or end.tzinfo is None or end <= start:
                raise ValueError("invalid OOS window")
        except (KeyError, TypeError, ValueError):
            reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")

    count_fields = ("wins", "losses", "breakevens", "timeouts")
    if any(type(report.get(field)) is not int or report[field] < 0 for field in count_fields):
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    elif sum(report[field] for field in count_fields[:3]) != report.get("resolved_closed_trade_count"):
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")

    if not isinstance(report.get("long_short_split"), dict) or not report["long_short_split"]:
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    if not isinstance(report.get("regime_split"), dict) or not report["regime_split"]:
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    for field in ("net_expectancy_after_costs", "profit_factor_after_costs", "maximum_drawdown"):
        if not _finite_number(report.get(field)):
            reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    if _finite_number(report.get("profit_factor_after_costs")) and report["profit_factor_after_costs"] < 0:
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    if _finite_number(report.get("maximum_drawdown")) and report["maximum_drawdown"] < 0:
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")

    fee_report = report.get("fee_and_slippage_model")
    if (
        not isinstance(fee_report, dict)
        or fee_report.get("status") != "VERIFIED"
        or fee_report.get("evidence_sha256") != cost_model.get("evidence_sha256")
    ):
        reasons.append("INDEPENDENT_OOS_COST_MODEL_MISMATCH")
    out_sample = report.get("out_of_sample_results")
    if not isinstance(out_sample, dict) or out_sample.get("status") != "PASS":
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    else:
        resolved = report.get("resolved_closed_trade_count")
        expected_rate = (
            round(100.0 * report["wins"] / resolved, 2)
            if type(resolved) is int and resolved > 0
            else None
        )
        if (
            not _finite_number(report.get("win_rate_pct"))
            or expected_rate is None
            or abs(float(report["win_rate_pct"]) - expected_rate) > 0.01
            or out_sample.get("resolved_closed_trade_count") != resolved
            or not _finite_number(out_sample.get("win_rate_pct"))
            or abs(float(out_sample["win_rate_pct"]) - expected_rate) > 0.01
        ):
            reasons.append("INDEPENDENT_OOS_METRICS_INCONSISTENT")
    return reasons


def daily_signal_counts(candidates: list[dict], *, performance_cohort: str) -> dict:
    """Count only cohort-qualified actionable candidates; the daily limit is never a quota."""
    counts: dict[str, int] = {}
    seen: set[str] = set()
    invalid = 0
    for row in candidates:
        if not isinstance(row, dict):
            invalid += 1
            continue
        if performance_cohort == "PRECISION_ENTRY_PAPER_ELIGIBLE":
            actionable = _precision_candidate_valid(row)
            timestamp = row.get("entry_time")
        elif performance_cohort == "PREAPPROVAL_PAPER_ELIGIBLE":
            actionable = row.get("preapproval_paper_eligible") is True
            timestamp = row.get("candidate_time", row.get("observed_at"))
        elif performance_cohort == "GATE_APPROVED_ONLY":
            actionable = row.get("final_gate_decision") in ("LONG", "SHORT")
            timestamp = row.get("candidate_time", row.get("observed_at"))
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
            day = _utc_day(timestamp)
        except (TypeError, ValueError, OverflowError, OSError):
            invalid += 1
            continue
        counts[day] = counts.get(day, 0) + 1
    return {
        "counts_by_utc_day": dict(sorted(counts.items())),
        "max_signals_in_any_utc_day": max(counts.values(), default=0),
        "invalid_actionable_records": invalid,
    }


def evaluate_acceptance(
    *,
    root: str | Path,
    metrics: dict,
    candidates: list[dict],
    independent_oos: dict | None = None,
) -> dict:
    """Evaluate claims conservatively; precision claims are derived from the 1m ledger."""
    contract, digest = load_contract(root)
    gate = contract["paper_performance_gate"]
    cap = contract["signal_constraints"]["max_actionable_signals_per_utc_day"]
    minimum = int(gate["minimum_resolved_closed_trades"])
    target = float(gate["win_rate_pct"])
    reasons = []
    cohort = gate.get("performance_cohort", "GATE_APPROVED_ONLY")

    precision_summary = None
    if cohort == "PRECISION_ENTRY_PAPER_ELIGIBLE":
        precision = _precision_ledger_metrics(root)
        resolved = precision["resolved"]
        win_rate = precision["win_rate_pct"]
        unscorable = precision["unscorable_outcomes"]
        unmatched = precision["unmatched_outcome_records"]
        ambiguous = precision["ambiguous_outcome_links"] + precision["duplicate_candidate_ids"]
        candidates_for_cap = precision["candidate_rows"]
        cost = precision["cost_model"]
        independent_oos = precision["independent_oos"]
        if precision["ledger_missing"]:
            reasons.append("PRECISION_ENTRY_LEDGER_MISSING")
        if precision["invalid_candidate_records"]:
            reasons.append("INVALID_PRECISION_CANDIDATE_RECORDS")
        if precision["duplicate_candidate_ids"]:
            reasons.append("AMBIGUOUS_PRECISION_CANDIDATE_IDS")
        if precision["duplicate_setup_ids"]:
            reasons.append("DUPLICATE_PRECISION_SETUP_CANDIDATES")
        precision_summary = {
            "candidate_records": precision["candidate_count"],
            "valid_candidate_records": precision["valid_candidate_count"],
            "outcome_records": precision["outcome_count"],
            "wins": precision["wins"],
            "losses": precision["losses"],
            "timeouts": precision["timeouts"],
            "resolved_closed_trades": resolved,
            "win_rate_pct": win_rate,
            "unresolved_candidates": precision["unresolved_candidates"],
            "invalid_candidate_records": precision["invalid_candidate_records"],
            "unmatched_outcome_records": unmatched,
            "ambiguous_outcome_links": ambiguous,
            "duplicate_setup_ids": precision["duplicate_setup_ids"],
            "unscorable_outcomes": unscorable,
            "source_sha256": precision["source_sha256"],
        }
    else:
        if cohort == "PREAPPROVAL_PAPER_ELIGIBLE":
            resolved = int(metrics.get("preapproval_paper_resolved", metrics.get("resolved", 0)) or 0)
            win_rate = metrics.get("preapproval_paper_win_rate_pct", metrics.get("win_rate_pct"))
            unscorable = int(metrics.get("preapproval_paper_unscorable_outcomes", metrics.get("unscorable_outcomes", 0)) or 0)
        elif cohort == "GATE_APPROVED_ONLY":
            resolved = int(metrics.get("eligible_resolved", metrics.get("resolved", 0)) or 0)
            win_rate = metrics.get("eligible_win_rate_pct", metrics.get("win_rate_pct"))
            unscorable = int(metrics.get("eligible_unscorable_outcomes", metrics.get("unscorable_outcomes", 0)) or 0)
        else:
            raise ValueError("unsupported performance cohort in acceptance contract")
        unmatched = int(metrics.get("unmatched_outcome_records", metrics.get("unmatched_outcomes", 0)) or 0)
        ambiguous = int(metrics.get("ambiguous_legacy_timestamp_matches", metrics.get("ambiguous_outcomes", 0)) or 0)
        candidates_for_cap = candidates
        cost = metrics.get("cost_model", {})

    if resolved < minimum:
        reasons.append("MINIMUM_RESOLVED_TRADES_NOT_MET")
    if not _finite_number(win_rate):
        reasons.append("INVALID_IN_SAMPLE_WIN_RATE")
    elif float(win_rate) <= target:
        reasons.append("STRICT_WIN_RATE_GT_90_NOT_MET")
    if unmatched:
        reasons.append("UNMATCHED_OUTCOMES_PRESENT")
    if ambiguous:
        reasons.append("AMBIGUOUS_OUTCOME_LINKS_PRESENT")
    if unscorable:
        reasons.append("UNSCORABLE_OUTCOMES_PRESENT")

    daily = daily_signal_counts(candidates_for_cap, performance_cohort=cohort)
    if daily["invalid_actionable_records"]:
        reasons.append("INVALID_ACTIONABLE_SIGNAL_RECORDS")
    if daily["max_signals_in_any_utc_day"] > cap:
        reasons.append("DAILY_SIGNAL_CAP_EXCEEDED")

    if (
        cost.get("status") != "VERIFIED"
        or cost.get("fees_slippage_verified") is not True
        or not _valid_sha256(cost.get("evidence_sha256"))
        or not _finite_number(cost.get("fee_fraction_per_side"))
        or not _finite_number(cost.get("slippage_fraction_per_side"))
        or cost.get("fee_fraction_per_side", -1) < 0
        or cost.get("slippage_fraction_per_side", -1) < 0
    ):
        reasons.append("VERIFIED_FEE_SLIPPAGE_MODEL_MISSING")

    if not isinstance(independent_oos, dict) or independent_oos.get("status") != "PASS":
        reasons.append("INDEPENDENT_OUT_OF_SAMPLE_EVIDENCE_MISSING")
    else:
        oos_count = independent_oos.get("resolved_closed_trade_count")
        if type(oos_count) is not int or oos_count < 0:
            reasons.append("INDEPENDENT_OOS_SAMPLE_INVALID")
        elif oos_count < minimum:
            reasons.append("INDEPENDENT_OOS_SAMPLE_TOO_SMALL")
        oos_wr = independent_oos.get("win_rate_pct")
        if not _finite_number(oos_wr):
            reasons.append("INDEPENDENT_OOS_WIN_RATE_INVALID")
        elif float(oos_wr) <= target:
            reasons.append("INDEPENDENT_OOS_WIN_RATE_NOT_ABOVE_90")
        if not _valid_sha256(independent_oos.get("evidence_sha256")):
            reasons.append("INDEPENDENT_OOS_PROVENANCE_MISSING")
        reasons.extend(_oos_report_completeness_reasons(independent_oos, cost))

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
        "target_met_on_in_sample_metrics": bool(
            resolved >= minimum
            and _finite_number(win_rate)
            and float(win_rate) > target
            and not unmatched
            and not ambiguous
            and not unscorable
        ),
        "daily_signal_cap": cap,
        "daily_signal_counts": daily,
        "unmatched_outcome_records": unmatched,
        "ambiguous_outcome_links": ambiguous,
        "unscorable_outcomes": unscorable,
        "independent_oos_status": independent_oos.get("status") if isinstance(independent_oos, dict) else "MISSING",
        "cost_model_status": cost.get("status", "MISSING"),
        "precision_entry_ledger": precision_summary,
        "reasons": reasons,
        "execution_enabled": False,
        "orders_placed": False,
    }
