from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from forward.strategy_family_paper_cohort_v1 import (
    _family_candidate,
    _resolve,
    reconcile_family_paper_cohorts,
)
from forward.strategy_family_router_v1 import (
    RANGE_MEAN_REVERSION_RESEARCH_V1,
    TREND_BREAKOUT_V2,
)


def decision_record(*, family="trend_breakout", candidate_time=1_700_000_000,
                    risk_state="RISK_APPROVED", final_decision="LONG",
                    confirmation_state="CONFIRMED_LONG", direction="LONG",
                    geometry=None):
    profile = TREND_BREAKOUT_V2 if family == "trend_breakout" else RANGE_MEAN_REVERSION_RESEARCH_V1
    observed = datetime.fromtimestamp(candidate_time, timezone.utc).isoformat()
    route = {
        "family_id": profile.family_id,
        "family_version": profile.version,
        "activation_state": profile.activation_state,
        "candidate_generation_authorized": False,
        "execution_enabled": False,
        "orders_placed": False,
    }
    candidate = {
        "family_id": profile.family_id,
        "family_version": profile.version,
        "state": "CANDIDATE_" + direction,
        "direction": direction,
        "observed_at": observed,
        "evidence_sha256": "a" * 64,
        "execution_enabled": False,
        "orders_placed": False,
    }
    if family == "range_mean_reversion":
        candidate.update({
            "entry_reference": 100,
            "stop_loss": 101 if direction == "SHORT" else 99,
            "take_profit": 97 if direction == "SHORT" else 103,
            "candidate_generation_authorized": False,
        })
        confirmation_state = "RESEARCH_CONFIRMED_" + direction
        risk_state = "RISK_REJECTED"
        final_decision = "NO_TRADE"
    else:
        confirmation_state = confirmation_state
        entry, stop, target = geometry or (100, 99, 103)
    context_gate = {
        "strategy_family_route": route,
        "strategy_family_confirmation": {"state": confirmation_state},
    }
    context = {
        "schema": "hes_strategy_family_candidate_context_v1",
        "context_version": "hes-strategy-family-context-v1.0.0",
        "family_id": profile.family_id,
        "family_version": profile.version,
        "family_activation_state": profile.activation_state,
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "setup_timeframe": "15m",
        "candidate": candidate,
        "gate_evidence": context_gate,
        "candidate_sha256": hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest(),
        "gate_evidence_sha256": hashlib.sha256(json.dumps(context_gate, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest(),
        "candidate_generation_authorized": False,
        "confirmation_approved": False,
        "risk_approved": False,
        "execution_enabled": False,
        "orders_placed": False,
    }
    context["context_sha256"] = hashlib.sha256(json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    record = {
        "event_id": f"hes-v2-BTC_USDT-15m-{candidate_time}",
        "candidate_time": candidate_time,
        "observed_at": observed,
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "evidence_source": "gateio_public_spot",
        "decision": final_decision,
        "risk_state": risk_state,
        "proposal_entry": 100 if family == "trend_breakout" else None,
        "proposal_stop_loss": 99 if family == "trend_breakout" else None,
        "proposal_take_profit": 103 if family == "trend_breakout" else None,
        "strategy_family_route": route,
        "strategy_family_candidate": candidate,
        "strategy_family_confirmation": {"state": confirmation_state},
        "strategy_family_context": context,
        "strategy_family_context_status": "VERIFIED_EVIDENCE_ONLY_NOT_AUTHORIZED",
        "execution_enabled": False,
        "orders_placed": False,
    }
    return record


def setup_root(tmp_path: Path):
    (tmp_path / "data" / "forward").mkdir(parents=True)
    (tmp_path / "forward").mkdir()
    (tmp_path / "forward" / "paper_risk_context_v1.json").write_text(json.dumps({
        "fee_fraction_per_side": 0.001,
        "slippage_fraction_per_side": 0.0005,
    }))
    return tmp_path


def write_journal(root, rows):
    path = root / "data" / "forward" / "trade_journal_v2.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def test_extracts_trend_candidate_with_proposal_geometry_and_exact_family_binding():
    row = decision_record()
    candidate, reason = _family_candidate(row)
    assert reason is None
    assert candidate["family_id"] == "trend_breakout"
    assert candidate["entry"] == 100
    assert candidate["acceptance_eligible"] is True
    assert candidate["execution_enabled"] is False


def test_range_candidate_is_shadow_only_and_never_risk_approved():
    row = decision_record(
        family="range_mean_reversion",
        direction="SHORT",
    )
    candidate, reason = _family_candidate(row)
    assert reason is None
    assert candidate["family_id"] == "range_mean_reversion"
    assert candidate["entry"] == 100
    assert candidate["family_confirmation_state"] == "RESEARCH_CONFIRMED_SHORT"
    assert candidate["risk_gate_state"] == "RISK_REJECTED"
    assert candidate["acceptance_eligible"] is False
    assert candidate["research_shadow_only"] is True


def test_rejects_unattributed_legacy_candidate_without_guessing_family():
    row = decision_record()
    row.pop("strategy_family_candidate")
    candidate, reason = _family_candidate(row)
    assert candidate is None
    assert reason == "FAMILY_EVIDENCE_MISSING"


def test_same_candle_stop_and_target_uses_conservative_loss():
    row = decision_record()
    candidate, reason = _family_candidate(row)
    assert reason is None
    outcome = _resolve(candidate, [{
        "close_time": candidate["candidate_time"] + 900,
        "high": 104, "low": 98, "close": 101,
    }], {
        "status": "ASSUMPTION_BASED",
        "fee_fraction_per_side": 0.001,
        "slippage_fraction_per_side": 0.0005,
    })
    assert outcome["ambiguous_same_candle"] is True
    assert outcome["resolution_type"] == "STOP_AND_TARGET_SAME_CANDLE_CONSERVATIVE_LOSS"
    assert outcome["outcome"] == "losses"
    assert outcome["execution_enabled"] is False


def test_reconciles_each_family_independently_and_keeps_range_shadow_separate(tmp_path):
    root = setup_root(tmp_path)
    trend = decision_record()
    range_row = decision_record(
        family="range_mean_reversion",
        candidate_time=1_700_000_900,
        direction="SHORT",
    )
    write_journal(root, [trend, range_row])
    bars = [
        {"close_time": 1_700_000_900, "high": 104, "low": 100, "close": 103},
        {"close_time": 1_700_001_800, "high": 100.5, "low": 96, "close": 97},
    ]
    result = reconcile_family_paper_cohorts(root=root, rows_15m=bars, write=True)
    assert result["candidate_records"] == 2
    assert result["outcome_records"] == 2
    assert result["new_candidates_appended"] == 2
    assert result["new_outcomes_resolved"] == 2
    assert result["families"]["trend_breakout"]["acceptance_eligible_candidate_count"] == 1
    assert result["families"]["trend_breakout"]["acceptance_eligible_metrics"]["wins"] == 1
    assert result["families"]["range_mean_reversion"]["acceptance_eligible_candidate_count"] == 0
    assert result["families"]["range_mean_reversion"]["research_shadow_metrics"]["resolved_closed_trade_count"] == 1
    assert result["families"]["range_mean_reversion"]["research_shadow_metrics"]["wins"] == 1
    assert result["family_acceptance"]["status"] == "NOT_MET"
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False
    assert result["risk_gate_modified"] is False
    # Idempotent second pass: no duplicate candidate or outcome append.
    second = reconcile_family_paper_cohorts(root=root, rows_15m=bars, write=True)
    assert second["new_candidates_appended"] == 0
    assert second["new_outcomes_resolved"] == 0
    assert second["candidate_records"] == 2
    assert second["outcome_records"] == 2


def test_cross_family_outcome_cannot_be_joined_to_another_family_candidate(tmp_path):
    root = setup_root(tmp_path)
    trend = decision_record()
    write_journal(root, [trend])
    first = reconcile_family_paper_cohorts(root=root, rows_15m=[], write=True)
    candidate_id = "hes-family-paper-trend_breakout-" + trend["event_id"]
    outcome_path = root / "data" / "forward" / "strategy_family_paper_outcomes_v1.jsonl"
    wrong = {
        "schema": "hes_strategy_family_paper_outcome_v1",
        "event_id": "wrong-family-outcome",
        "candidate_event_id": candidate_id,
        "family_id": "range_mean_reversion",
        "family_version": RANGE_MEAN_REVERSION_RESEARCH_V1.version,
        "direction": "LONG",
        "execution_enabled": False,
        "orders_placed": False,
        "outcome": "wins",
        "net_r": 2.0,
    }
    outcome_path.write_text(json.dumps(wrong) + "\n")
    result = reconcile_family_paper_cohorts(root=root, rows_15m=[], write=False)
    assert result["families"]["trend_breakout"]["resolved_outcome_count"] == 0
    assert result["families"]["trend_breakout"]["pending_candidate_count"] == 1
    assert result["families"]["range_mean_reversion"]["family_mismatch_count"] == 1
    assert result["family_acceptance"]["status"] == "NOT_MET"


def test_rejects_noncanonical_source_and_authority_boundary_violations():
    row = decision_record()
    row["evidence_source"] = "other_source"
    candidate, reason = _family_candidate(row)
    assert candidate is None
    assert reason == "NON_CANONICAL_MARKET_SCOPE"

    row = decision_record()
    row["strategy_family_route"]["execution_enabled"] = True
    candidate, reason = _family_candidate(row)
    assert candidate is None
    assert reason == "FAMILY_ROUTE_AUTHORITY_BOUNDARY_VIOLATION"


def test_rejects_family_candidate_that_differs_from_hashed_context_candidate():
    row = decision_record()
    row["strategy_family_candidate"]["tampered_field"] = "changed"
    candidate, reason = _family_candidate(row)
    assert candidate is None
    assert reason == "FAMILY_CONTEXT_DIGEST_MISMATCH"