import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_strategy_policy_v2_forward_eval.py"
spec = importlib.util.spec_from_file_location("strategy_policy_v2_forward_eval_projection", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _hashes():
    return {
        "mother_snapshot_sha256": "a" * 64,
        "mother_audit_sha256": "b" * 64,
        "mother_trace_id": "c" * 64,
        "news_snapshot_sha256": "d" * 64,
        "news_brief_sha256": "e" * 64,
    }


def _mother_event():
    candidate = {
        "event_id": "family-paper:test-001", "candidate_observed_at": 1_700_000_000,
        "status": "CONFIRMED_RISK_APPROVED_PAPER_ONLY", "direction": "SHORT",
        "reference_price": 100.0, "stop_loss": 110.0, "take_profit": 70.0, "rr": 3.0,
        "entry_semantics": "CLOSED_15M_REFERENCE_NOT_EXECUTION_FILL",
        "parent_family_id": "trend_breakout", "paper_candidate_generation_authorized": True,
        "decision_authority": False, "risk_gate_bypass": False,
        "execution_enabled": False, "orders_placed": False, "precision_entry_1m_ready": True,
        "regime_consensus": {"status": "ALIGNED", "direction": "SHORT", "structure_regime": "DOWNTREND"},
        "confirmation": {"state": "CONFIRMED_SHORT", "reason_codes": []},
        "risk": {"state": "RISK_APPROVED", "reason_codes": []},
        "strategy_family_route": {
            "family_id": "trend_breakout", "family_version": "trend-breakout-v2",
            "activation_state": "CANDIDATE_LOCKED_NOT_ACTIVE",
            "paper_candidate_generation_authorized": True,
            "candidate_generation_authorized": False,
            "execution_enabled": False, "orders_placed": False,
        },
    }
    return {
        "schema": "hes_mother_decision_journal_event_v1", "event_id": "hes-mother:test-001",
        "observed_at": "2026-11-22T15:00:00+00:00", "source": "gateio_public_spot",
        "symbol": "BTC_USDT", "timeframe": "15m", "decision": "NO_TRADE",
        "reason_codes": ["FINAL_POLICY_APPROVAL_REQUIRED"], "witness_verified": True,
        "execution_enabled": False, "orders_placed": False, "outcomes_inferred": False,
        "source_hashes": _hashes(),
        "gate_evidence": {"strategy_family_paper_lane": {
            "paper_candidate_generation_authorized": True, "selected_candidate": candidate,
        }},
    }


def test_mother_candidate_projects_once_into_existing_preapproval_paper_ledger(tmp_path):
    journal = tmp_path / "trade_journal_v2.jsonl"
    candidates = tmp_path / "strategy_policy_v2_eval_candidates.jsonl"
    journal.write_text(json.dumps(_mother_event()) + "\n")
    first = mod.project_mother_family_candidates(
        journal_path=journal, candidates_path=candidates, now=1_700_000_100,
    )
    second = mod.project_mother_family_candidates(
        journal_path=journal, candidates_path=candidates, now=1_700_000_100,
    )
    assert len(first) == 1 and second == []
    row = first[0]
    assert row["candidate_event_id"] == "family-paper:test-001"
    assert row["strategy_family_id"] == "trend_breakout"
    assert row["preapproval_paper_eligible"] is True
    assert row["final_gate_decision"] == "NO_TRADE"
    assert row["entry_semantics"] == "CLOSED_15M_REFERENCE_NOT_EXECUTION_FILL"
    assert row["execution_enabled"] is False and row["orders_placed"] is False
    assert len(candidates.read_text().splitlines()) == 1


def test_mother_candidate_projection_rejects_live_authority_or_unwitnessed_rows(tmp_path):
    journal = tmp_path / "trade_journal_v2.jsonl"
    candidates = tmp_path / "strategy_policy_v2_eval_candidates.jsonl"
    row = _mother_event()
    row["witness_verified"] = False
    journal.write_text(json.dumps(row) + "\n")
    assert mod.project_mother_family_candidates(
        journal_path=journal, candidates_path=candidates, now=1_700_000_100,
    ) == []
    row = _mother_event()
    row["witness_verified"] = True
    row["gate_evidence"]["strategy_family_paper_lane"]["selected_candidate"]["strategy_family_route"]["candidate_generation_authorized"] = True
    journal.write_text(json.dumps(row) + "\n")
    assert mod.project_mother_family_candidates(
        journal_path=journal, candidates_path=candidates, now=1_700_000_100,
    ) == []


def test_active_candidate_reconciliation_recovers_only_unresolved_candidates(tmp_path, monkeypatch):
    candidates = tmp_path / "candidates.jsonl"
    outcomes = tmp_path / "outcomes.jsonl"
    candidates.write_text("\n".join(json.dumps({
        "candidate_event_id": cid, "candidate_time": 1_700_000_000, "direction": "SHORT",
        "entry": 100, "stop_loss": 110, "take_profit": 70,
        "execution_enabled": False, "orders_placed": False,
    }) for cid in ("cand-a", "cand-b")) + "\n")
    outcomes.write_text(json.dumps({"candidate_event_id": "cand-a", "outcome": "wins"}) + "\n")
    monkeypatch.setattr(mod, "CAND", candidates)
    monkeypatch.setattr(mod, "OUT", outcomes)
    state = {"active": []}
    assert mod.reconcile_active_candidates(state) == 1
    assert [x["candidate_event_id"] for x in state["active"]] == ["cand-b"]
    assert mod.reconcile_active_candidates(state) == 0


def test_outcome_event_ids_are_unique_for_multiple_family_candidates_on_same_candle():
    a = mod._outcome_event_id("family-paper:a", "outcome")
    b = mod._outcome_event_id("family-paper:b", "outcome")
    assert a != b
    assert a == mod._outcome_event_id("family-paper:a", "outcome")
    assert mod._outcome_event_id("family-paper:a", "timeout") != a
