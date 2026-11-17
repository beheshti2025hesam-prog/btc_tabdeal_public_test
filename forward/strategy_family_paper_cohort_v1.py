"""Append-only, family-isolated paper outcome resolver and reconciliation.

Consumes only the existing Gate.io 15m decision journal and closed-candle rows.
It never changes the Risk Gate or turns a research candidate into an executable
signal. Research-confirmed Range candidates are shadow-scored and remain
ineligible for family promotion while the shared Risk Gate vetoes them.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .forward_journal_v1 import ForwardJournalV1
from .paper_outcome_resolver_v1 import resolve_paper_outcome
from .strategy_family_router_v1 import (
    RANGE_MEAN_REVERSION_RESEARCH_V1,
    TREND_BREAKOUT_V2,
)

SCHEMA = "hes_strategy_family_paper_reconciliation_v1"
VERSION = "hes-strategy-family-paper-cohort-v1.0.0"
SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"
TIMEFRAME = "15m"
MAX_HOLD_SECONDS = 86_400
_PROFILES = {
    TREND_BREAKOUT_V2.family_id: TREND_BREAKOUT_V2,
    RANGE_MEAN_REVERSION_RESEARCH_V1.family_id: RANGE_MEAN_REVERSION_RESEARCH_V1,
}
_ALLOWED_CONFIRMATIONS = {
    "CONFIRMED_LONG": ("trend_breakout", "LONG"),
    "CONFIRMED_SHORT": ("trend_breakout", "SHORT"),
    "RESEARCH_CONFIRMED_LONG": ("range_mean_reversion", "LONG"),
    "RESEARCH_CONFIRMED_SHORT": ("range_mean_reversion", "SHORT"),
}
_EVENT_TIME_RE = re.compile(r"-(\d{9,})$")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError(f"INCOMPLETE_JSONL_TAIL:{path.name}")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_no, raw_line in enumerate(raw.splitlines(), 1):
        if not raw_line.strip():
            raise ValueError(f"BLANK_JSONL_RECORD:{path.name}:{line_no}")
        row = json.loads(raw_line.decode("utf-8", errors="strict"))
        if not isinstance(row, dict):
            raise ValueError(f"NON_OBJECT_JSONL_RECORD:{path.name}:{line_no}")
        event_id = row.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError(f"MISSING_EVENT_ID:{path.name}:{line_no}")
        if event_id in seen:
            raise ValueError(f"DUPLICATE_EVENT_ID:{path.name}:{line_no}")
        seen.add(event_id)
        rows.append(row)
    return rows


def _aware_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _finite_positive(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _candidate_time(record: Mapping[str, Any]) -> int | None:
    value = record.get("candidate_time", record.get("candle_close_time"))
    if type(value) is int and value > 0:
        return value
    event_id = record.get("event_id")
    match = _EVENT_TIME_RE.search(event_id) if isinstance(event_id, str) else None
    return int(match.group(1)) if match else None


def _family_candidate(record: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Extract only an explicitly routed, confirmed, provenance-bound candidate."""
    gate = record.get("gate_evidence")
    gate = gate if isinstance(gate, Mapping) else {}
    route = record.get("strategy_family_route") or gate.get("strategy_family_route")
    candidate = record.get("strategy_family_candidate") or gate.get("strategy_family_candidate")
    confirmation = record.get("strategy_family_confirmation") or gate.get("strategy_family_confirmation")
    if not isinstance(route, Mapping) or not isinstance(candidate, Mapping) or not isinstance(confirmation, Mapping):
        return None, "FAMILY_EVIDENCE_MISSING"
    family_id = route.get("family_id")
    profile = _PROFILES.get(family_id)
    if profile is None:
        return None, "UNKNOWN_OR_MISSING_FAMILY"
    family_version = route.get("family_version")
    if family_version != profile.version or candidate.get("family_id") != family_id or candidate.get("family_version") != family_version:
        return None, "FAMILY_ID_OR_VERSION_MISMATCH"
    confirmation_state = confirmation.get("state")
    expected = _ALLOWED_CONFIRMATIONS.get(confirmation_state)
    if expected != (family_id, candidate.get("direction")):
        return None, "FAMILY_CONFIRMATION_NOT_VALID"
    if route.get("candidate_generation_authorized") is not False or route.get("execution_enabled") is not False or route.get("orders_placed") is not False:
        return None, "FAMILY_ROUTE_AUTHORITY_BOUNDARY_VIOLATION"
    if candidate.get("candidate_generation_authorized", False) is not False or candidate.get("execution_enabled", False) is not False or candidate.get("orders_placed", False) is not False:
        return None, "FAMILY_CANDIDATE_AUTHORITY_BOUNDARY_VIOLATION"
    if record.get("execution_enabled") is not False or record.get("orders_placed") is not False:
        return None, "DECISION_EXECUTION_BOUNDARY_VIOLATION"
    context = record.get("strategy_family_context") or gate.get("strategy_family_context")
    context_status = record.get("strategy_family_context_status") or gate.get("strategy_family_context_status")
    if not isinstance(context, Mapping) or context_status != "VERIFIED_EVIDENCE_ONLY_NOT_AUTHORIZED":
        return None, "FAMILY_CONTEXT_NOT_VERIFIED"
    context_hash = context.get("context_sha256")
    evidence_hash = candidate.get("evidence_sha256")
    context_candidate = context.get("candidate")
    context_gate = context.get("gate_evidence")
    if not (isinstance(context_hash, str) and len(context_hash) == 64
            and isinstance(evidence_hash, str) and len(evidence_hash) == 64
            and isinstance(context_candidate, Mapping) and isinstance(context_gate, Mapping)):
        return None, "FAMILY_PROVENANCE_HASH_MISSING"
    try:
        context_base = {key: value for key, value in context.items() if key != "context_sha256"}
        candidate_digest = context.get("candidate_sha256")
        if (_sha(context_base) != context_hash
                or _sha(context_candidate) != candidate_digest
                or _sha(candidate) != candidate_digest
                or _sha(candidate) != _sha(context_candidate)
                or _sha(context_gate) != context.get("gate_evidence_sha256")):
            return None, "FAMILY_CONTEXT_DIGEST_MISMATCH"
    except (TypeError, ValueError):
        return None, "FAMILY_CONTEXT_PAYLOAD_INVALID"
    if (context.get("family_id") != family_id or context.get("family_version") != family_version
            or context.get("family_activation_state") != profile.activation_state
            or context.get("source") != SOURCE or context.get("symbol") != SYMBOL
            or context.get("setup_timeframe") != TIMEFRAME
            or context_candidate.get("family_id") != family_id
            or context_candidate.get("family_version") != family_version
            or context_candidate.get("direction") != candidate.get("direction")
            or context_candidate.get("evidence_sha256") != evidence_hash
            or context.get("candidate_generation_authorized") is not False
            or context.get("confirmation_approved") is not False
            or context.get("risk_approved") is not False
            or context.get("execution_enabled") is not False
            or context.get("orders_placed") is not False):
        return None, "FAMILY_CONTEXT_IDENTITY_OR_AUTHORITY_MISMATCH"
    context_route = context_gate.get("strategy_family_route")
    context_confirmation = context_gate.get("strategy_family_confirmation")
    if (not isinstance(context_route, Mapping) or context_route.get("family_id") != family_id
            or context_route.get("family_version") != family_version
            or context_route.get("activation_state") != profile.activation_state
            or not isinstance(context_confirmation, Mapping)
            or context_confirmation.get("state") != confirmation_state):
        return None, "FAMILY_CONTEXT_GATE_BINDING_MISMATCH"
    if record.get("evidence_source") != SOURCE or record.get("symbol") != SYMBOL or record.get("timeframe") != TIMEFRAME:
        return None, "NON_CANONICAL_MARKET_SCOPE"
    direction = candidate.get("direction")
    state = candidate.get("state")
    if direction not in ("LONG", "SHORT") or state != ("CANDIDATE_" + direction):
        return None, "CANDIDATE_DIRECTION_OR_STATE_INVALID"
    candidate_time = _candidate_time(record)
    observed = _aware_timestamp(candidate.get("observed_at")) or _aware_timestamp(record.get("observed_at"))
    if candidate_time is None or observed is None or abs(observed.timestamp() - candidate_time) > 960:
        return None, "CANDIDATE_TIME_BINDING_INVALID"
    entry = _finite_positive(candidate.get("entry", candidate.get("entry_reference")))
    if entry is None:
        entry = _finite_positive(record.get("proposal_entry", record.get("entry")))
    stop = _finite_positive(candidate.get("stop_loss", record.get("proposal_stop_loss", record.get("stop_loss"))))
    target = _finite_positive(candidate.get("take_profit", record.get("proposal_take_profit", record.get("take_profit"))))
    if entry is None or stop is None or target is None:
        return None, "CANDIDATE_GEOMETRY_MISSING_OR_INVALID"
    geometry_ok = (stop < entry < target) if direction == "LONG" else (target < entry < stop)
    if not geometry_ok:
        return None, "CANDIDATE_GEOMETRY_DIRECTION_MISMATCH"
    decision_event_id = record.get("event_id")
    if not isinstance(decision_event_id, str) or not decision_event_id:
        return None, "DECISION_EVENT_ID_MISSING"
    risk_payload = gate.get("risk") if isinstance(gate.get("risk"), Mapping) else {}
    risk_state = record.get("risk_state") or risk_payload.get("state")
    final_decision = record.get("decision") or record.get("final_decision")
    acceptance_eligible = (
        confirmation_state in ("CONFIRMED_LONG", "CONFIRMED_SHORT")
        and risk_state == "RISK_APPROVED"
        and final_decision in ("LONG", "SHORT")
        and final_decision == direction
    )
    candidate_event_id = f"hes-family-paper-{family_id}-{decision_event_id}"
    return {
        "schema": "hes_strategy_family_paper_candidate_v1",
        "event_id": candidate_event_id,
        "candidate_event_id": candidate_event_id,
        "decision_event_id": decision_event_id,
        "family_id": family_id,
        "family_version": family_version,
        "family_activation_state": profile.activation_state,
        "source": SOURCE,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "candidate_time": candidate_time,
        "observed_at": observed.isoformat(),
        "direction": direction,
        "entry": entry,
        "entry_model": "CLOSED_CANDLE_REFERENCE_SIMULATION_NOT_EXCHANGE_FILL",
        "stop_loss": stop,
        "take_profit": target,
        "family_confirmation_state": confirmation_state,
        "risk_gate_state": risk_state or "UNKNOWN",
        "final_decision": final_decision or "UNKNOWN",
        "acceptance_eligible": acceptance_eligible,
        "research_shadow_only": not acceptance_eligible,
        "candidate_evidence_sha256": evidence_hash,
        "family_context_sha256": context_hash,
        "run_id": record.get("run_id"),
        "code_release_id": record.get("code_release_id"),
        "run_manifest_sha256": record.get("run_manifest_sha256"),
        "execution_enabled": False,
        "orders_placed": False,
    }, None


def _cost_model(root: Path) -> dict[str, Any]:
    path = root / "forward" / "paper_risk_context_v1.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        fee = float(raw["fee_fraction_per_side"])
        slip = float(raw["slippage_fraction_per_side"])
        if not all(math.isfinite(x) and x >= 0 for x in (fee, slip)):
            raise ValueError
        model = {
            "status": "ASSUMPTION_BASED",
            "fees_slippage_verified": False,
            "fee_fraction_per_side": fee,
            "slippage_fraction_per_side": slip,
            "evidence_sha256": _file_sha(path),
            "note": "Simulation assumptions only; not verified exchange/account fills or fees.",
        }
        model["model_sha256"] = _sha(model)
        return model
    except (OSError, KeyError, TypeError, ValueError, OverflowError):
        return {
            "status": "UNAVAILABLE",
            "fees_slippage_verified": False,
            "fee_fraction_per_side": None,
            "slippage_fraction_per_side": None,
            "evidence_sha256": None,
            "note": "No usable cost assumptions; net outcome is not scorable.",
        }


def _resolve(candidate: Mapping[str, Any], rows_15m: Sequence[Mapping[str, Any]],
             cost: Mapping[str, Any]) -> dict[str, Any] | None:
    entry = float(candidate["entry"])
    stop = float(candidate["stop_loss"])
    target = float(candidate["take_profit"])
    direction = candidate["direction"]
    candidate_time = int(candidate["candidate_time"])
    fee = cost.get("fee_fraction_per_side")
    slip = cost.get("slippage_fraction_per_side")
    if type(fee) not in (int, float) or type(slip) not in (int, float):
        return None
    resolution = resolve_paper_outcome(candidate, rows_15m, max_hold_seconds=MAX_HOLD_SECONDS)
    if resolution is None:
        return None
    exit_price = float(resolution["exit_price"])
    exit_close = float(resolution["exit_close"])
    exit_time = int(resolution["exit_close_time"])
    resolution_type = str(resolution["reason"])
    ambiguous = bool(resolution["ambiguous_same_candle"])
    gross = (exit_price - entry) if direction == "LONG" else (entry - exit_price)
    cost_amount = (entry + exit_price) * (float(fee) + float(slip))
    net = gross - cost_amount
    risk = abs(entry - stop)
    if risk <= 0 or not math.isfinite(net):
        return None
    net_r = net / risk
    outcome = "wins" if net_r > 0 else "losses" if net_r < 0 else "breakevens"
    return {
        "schema": "hes_strategy_family_paper_outcome_v1",
        "event_id": "hes-family-paper-outcome-" + str(candidate["candidate_event_id"]),
        "candidate_event_id": candidate["candidate_event_id"],
        "decision_event_id": candidate["decision_event_id"],
        "family_id": candidate["family_id"],
        "family_version": candidate["family_version"],
        "candidate_time": candidate_time,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "direction": direction,
        "entry": entry,
        "stop_loss": stop,
        "take_profit": target,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_close": exit_close,
        "resolution_type": resolution_type,
        "price_path_outcome": resolution["outcome"],
        "ambiguous_same_candle": ambiguous,
        "timeout": resolution["timeout"],
        "outcome": outcome,
        "gross_pnl_per_unit": gross,
        "estimated_cost_per_unit": cost_amount,
        "net_pnl_per_unit": net,
        "net_r": net_r,
        "cost_model_status": cost.get("status"),
        "cost_model_evidence_sha256": cost.get("evidence_sha256"),
        "acceptance_eligible": candidate.get("acceptance_eligible") is True,
        "research_shadow_only": candidate.get("research_shadow_only") is True,
        "execution_enabled": False,
        "orders_placed": False,
    }


def _score(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    wins = sum(row.get("outcome") == "wins" for row in rows)
    losses = sum(row.get("outcome") == "losses" for row in rows)
    breakevens = sum(row.get("outcome") == "breakevens" for row in rows)
    timeouts = sum(row.get("timeout") is True for row in rows)
    resolved = wins + losses + breakevens
    rs = [float(row["net_r"]) for row in rows if type(row.get("net_r")) in (int, float) and math.isfinite(float(row["net_r"]))]
    gains = sum(value for value in rs if value > 0)
    drawdown = peak = equity = 0.0
    for value in rs:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "timeouts": timeouts,
        "resolved_closed_trade_count": resolved,
        "win_rate_pct": round(100.0 * wins / resolved, 2) if resolved else None,
        "net_expectancy_after_costs": round(sum(rs) / len(rs), 8) if rs else None,
        "profit_factor_after_costs": round(gains / abs(sum(value for value in rs if value < 0)), 8)
            if any(value < 0 for value in rs) else None,
        "maximum_drawdown": round(drawdown, 8) if rs else None,
        "net_r_sum": round(sum(rs), 8) if rs else None,
    }


def _family_report(family_id: str, profile: Any, all_candidates: list[dict[str, Any]],
                   all_outcomes: list[dict[str, Any]], cost: dict[str, Any],
                   source_hashes: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = [row for row in all_candidates if row.get("family_id") == family_id]
    outcomes = [row for row in all_outcomes if row.get("family_id") == family_id]
    by_candidate = {row["candidate_event_id"]: row for row in all_candidates}
    linked: list[tuple[dict[str, Any], dict[str, Any]]] = []
    unmatched = family_mismatch = safety_violations = 0
    outcome_counts = Counter(row.get("candidate_event_id") for row in outcomes)
    duplicate_outcomes = sum(count > 1 for count in outcome_counts.values())
    for outcome in outcomes:
        candidate = by_candidate.get(outcome.get("candidate_event_id"))
        if candidate is None:
            unmatched += 1
            continue
        if (candidate.get("family_id") != family_id
                or outcome.get("family_id") != family_id
                or outcome.get("family_id") != candidate.get("family_id")
                or outcome.get("family_version") != candidate.get("family_version")
                or outcome.get("direction") != candidate.get("direction")):
            family_mismatch += 1
            continue
        if outcome.get("execution_enabled") is not False or outcome.get("orders_placed") is not False:
            safety_violations += 1
            continue
        linked.append((candidate, outcome))
    duplicate_ids = {key for key, count in outcome_counts.items() if count > 1}
    linked = [(candidate, outcome) for candidate, outcome in linked
              if outcome.get("candidate_event_id") not in duplicate_ids]
    shadow_rows = [outcome for _, outcome in linked]
    eligible_rows = [outcome for candidate, outcome in linked if candidate.get("acceptance_eligible") is True]
    shadow_metrics = _score(shadow_rows)
    eligible_metrics = _score(eligible_rows)
    daily: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        if candidate.get("acceptance_eligible") is True:
            observed = _aware_timestamp(candidate.get("observed_at"))
            if observed:
                daily[observed.date().isoformat()] += 1
    risk_policy_status = "PASS" if any(row.get("acceptance_eligible") is True for row in candidates) else "NOT_MET"
    acceptance_blockers: list[str] = []
    if eligible_metrics["resolved_closed_trade_count"] < 100:
        acceptance_blockers.append("MINIMUM_100_RESOLVED_TRADES_NOT_MET")
    if eligible_metrics["win_rate_pct"] is None or eligible_metrics["win_rate_pct"] <= 90.0:
        acceptance_blockers.append("WIN_RATE_NOT_STRICTLY_ABOVE_90")
    if eligible_metrics["net_expectancy_after_costs"] is None or eligible_metrics["net_expectancy_after_costs"] <= 0:
        acceptance_blockers.append("NET_EXPECTANCY_AFTER_COSTS_NOT_POSITIVE")
    if eligible_metrics["profit_factor_after_costs"] is None or eligible_metrics["profit_factor_after_costs"] <= 1:
        acceptance_blockers.append("PROFIT_FACTOR_AFTER_COSTS_NOT_ABOVE_1")
    if eligible_metrics["maximum_drawdown"] is None:
        acceptance_blockers.append("MAXIMUM_DRAWDOWN_UNAVAILABLE")
    if not (cost.get("status") == "VERIFIED" and cost.get("fees_slippage_verified") is True):
        acceptance_blockers.append("VERIFIED_FEE_SLIPPAGE_MODEL_MISSING")
    if risk_policy_status != "PASS":
        acceptance_blockers.append("INDEPENDENT_RISK_POLICY_ACCEPTANCE_MISSING")
    if unmatched or family_mismatch or duplicate_outcomes or safety_violations:
        acceptance_blockers.append("FAMILY_OUTCOME_LINKAGE_OR_SAFETY_ERRORS")
    # OOS evidence is deliberately not synthesized from the in-sample ledger.
    independent_oos = None
    acceptance_blockers.append("INDEPENDENT_OOS_EVIDENCE_MISSING")
    evidence = {
        "family_id": family_id,
        "family_version": profile.version,
        "source_hashes": source_hashes,
        "candidate_ids": sorted(row.get("candidate_event_id", "") for row in candidates),
        "outcome_ids": sorted(row.get("event_id", "") for row in outcomes),
    }
    evidence_sha = _sha(evidence)
    cohort_id = f"{family_id}:{profile.version}:{evidence_sha[:16]}"
    report = {
        "schema": "hes_strategy_family_evaluation_report_v1",
        "status": "PASS" if not acceptance_blockers else "NOT_MET",
        "acceptance_blockers": list(dict.fromkeys(acceptance_blockers)),
        "family_id": family_id,
        "family_version": profile.version,
        "cohort_family_ids": [family_id],
        "cohort_id": cohort_id,
        "risk_policy_status": risk_policy_status,
        "execution_enabled": False,
        "orders_placed": False,
        "resolved_closed_trade_count": eligible_metrics["resolved_closed_trade_count"],
        "wins": eligible_metrics["wins"],
        "losses": eligible_metrics["losses"],
        "breakevens": eligible_metrics["breakevens"],
        "timeouts": eligible_metrics["timeouts"],
        "win_rate_pct": eligible_metrics["win_rate_pct"],
        "net_expectancy_after_costs": eligible_metrics["net_expectancy_after_costs"],
        "profit_factor_after_costs": eligible_metrics["profit_factor_after_costs"],
        "maximum_drawdown": eligible_metrics["maximum_drawdown"],
        "cost_model": cost,
        "independent_oos": independent_oos,
        "daily_actionable_signals_by_utc_day": dict(sorted(daily.items())),
        "evidence_sha256": evidence_sha,
        "source_hashes": source_hashes,
        "report_sha256": "",
    }
    report["report_sha256"] = _sha({key: value for key, value in report.items() if key != "report_sha256"})
    summary = {
        "family_id": family_id,
        "family_version": profile.version,
        "activation_state": profile.activation_state,
        "candidate_count": len(candidates),
        "resolved_outcome_count": len(linked),
        "pending_candidate_count": max(0, len(candidates) - len({outcome.get("candidate_event_id") for _, outcome in linked})),
        "unmatched_outcome_count": unmatched,
        "family_mismatch_count": family_mismatch,
        "duplicate_outcome_candidate_count": duplicate_outcomes,
        "safety_violation_count": safety_violations,
        "acceptance_eligible_candidate_count": sum(row.get("acceptance_eligible") is True for row in candidates),
        "acceptance_eligible_metrics": eligible_metrics,
        "research_shadow_metrics": shadow_metrics,
        "risk_policy_status": risk_policy_status,
        "cost_model_status": cost.get("status"),
        "independent_oos_status": "MISSING",
        "acceptance_status": report["status"],
        "acceptance_blockers": report["acceptance_blockers"],
        "execution_enabled": False,
        "orders_placed": False,
    }
    return summary, report


def reconcile_family_paper_cohorts(*, root: str | Path, rows_15m: Sequence[Mapping[str, Any]],
                                   write: bool = True) -> dict[str, Any]:
    """Idempotently append family candidates/outcomes and produce independent reports."""
    root = Path(root)
    base = root / "data" / "forward"
    journal_path = base / "trade_journal_v2.jsonl"
    candidate_path = base / "strategy_family_paper_candidates_v1.jsonl"
    outcome_path = base / "strategy_family_paper_outcomes_v1.jsonl"
    report_path = base / "strategy_family_paper_reconciliation_v1.json"
    journal_rows = _read_jsonl(journal_path)
    candidates = _read_jsonl(candidate_path)
    outcomes = _read_jsonl(outcome_path)
    candidate_by_id = {row["event_id"]: row for row in candidates}
    initial_candidate_count = len(candidates)
    outcome_by_id = {row["event_id"]: row for row in outcomes}
    rejects: Counter[str] = Counter()
    conflicts = 0
    candidate_writer = ForwardJournalV1(candidate_path)
    outcome_writer = ForwardJournalV1(outcome_path)
    preview_candidates: list[dict[str, Any]] = []

    for record in journal_rows:
        candidate, reason = _family_candidate(record)
        if candidate is None:
            route = record.get("strategy_family_route")
            if (reason == "FAMILY_EVIDENCE_MISSING" and isinstance(route, Mapping)
                    and route.get("family_id") in _PROFILES):
                rejects["UNATTRIBUTED_FAMILY_DECISION_NO_CANDIDATE"] += 1
            elif reason and reason != "FAMILY_EVIDENCE_MISSING":
                rejects[reason] += 1
            continue
        existing = candidate_by_id.get(candidate["event_id"])
        if existing is not None:
            if _sha(existing) != _sha(candidate):
                conflicts += 1
            continue
        if write:
            if candidate_writer.append_event(candidate):
                candidates.append(candidate)
                candidate_by_id[candidate["event_id"]] = candidate
        else:
            preview_candidates.append(candidate)
            candidate_by_id[candidate["event_id"]] = candidate

    candidates_for_report = candidates + preview_candidates
    cost = _cost_model(root)
    resolved_now = 0
    preview_outcomes: list[dict[str, Any]] = []
    if write:
        for candidate in candidates:
            outcome_id = "hes-family-paper-outcome-" + str(candidate["candidate_event_id"])
            if outcome_id in outcome_by_id:
                continue
            outcome = _resolve(candidate, rows_15m, cost)
            if outcome is None:
                continue
            if outcome_writer.append_event(outcome):
                outcomes.append(outcome)
                outcome_by_id[outcome_id] = outcome
                resolved_now += 1
    else:
        for candidate in candidates_for_report:
            outcome_id = "hes-family-paper-outcome-" + str(candidate["candidate_event_id"])
            if outcome_id in outcome_by_id:
                continue
            outcome = _resolve(candidate, rows_15m, cost)
            if outcome is not None:
                preview_outcomes.append(outcome)
    outcomes_for_report = outcomes + preview_outcomes

    source_hashes = {
        "decision_journal_sha256": _file_sha(journal_path),
        "candidate_ledger_sha256": _file_sha(candidate_path),
        "outcome_ledger_sha256": _file_sha(outcome_path),
        "paper_cost_context_sha256": cost.get("evidence_sha256"),
        "market_data_rows_sha256": _sha(list(rows_15m)),
    }
    families: dict[str, Any] = {}
    family_reports: dict[str, Any] = {}
    for family_id, profile in _PROFILES.items():
        summary, report = _family_report(family_id, profile, candidates_for_report, outcomes_for_report, cost, source_hashes)
        families[family_id] = summary
        family_reports[family_id] = report

    # Import lazily to avoid a module cycle and use the existing independent-family
    # acceptance contract rather than creating a second promotion policy.
    from .strategy_family_evaluation_v1 import evaluate_family_acceptance
    acceptance = evaluate_family_acceptance(family_reports)
    result = {
        "schema": SCHEMA,
        "version": VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "RECONCILED" if candidates_for_report else "NO_FAMILY_CANDIDATES_YET",
        "market_data_source": SOURCE,
        "symbol": SYMBOL,
        "setup_timeframe": TIMEFRAME,
        "candidate_records": len(candidates_for_report),
        "outcome_records": len(outcomes_for_report),
        "new_candidates_appended": max(0, len(candidates) - initial_candidate_count),
        "preview_candidate_records": len(preview_candidates),
        "new_outcomes_resolved": resolved_now,
        "preview_resolvable_outcomes": len(preview_outcomes),
        "candidate_conflict_count": conflicts,
        "candidate_extraction_rejections": dict(sorted(rejects.items())),
        "families": families,
        "family_reports": family_reports,
        "family_acceptance": acceptance,
        "acceptance_is_independent_per_family": True,
        "timestamp_fallback_matching": False,
        "execution_enabled": False,
        "orders_placed": False,
        "risk_gate_modified": False,
        "live_trading_authorized": False,
        "source_hashes": source_hashes,
    }
    result["report_sha256"] = _sha(result)
    if write:
        base.mkdir(parents=True, exist_ok=True)
        temp = report_path.with_suffix(report_path.suffix + ".tmp")
        temp.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, report_path)
    return result