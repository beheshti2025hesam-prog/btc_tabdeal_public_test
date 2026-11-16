from forward.precision_entry_setup_link_v1 import resolve_precision_setup_context
from forward.strategy_entry_context_v1 import build_entry_context


NOW = 1_800_003_600
RUN = {
    "run_id": "HESV2-test-run-0001",
    "code_release_id": "release-test",
    "run_manifest_sha256": "b" * 64,
}


def gate(direction="LONG", regime="UPTREND"):
    return {
        "risk": {"state": "RISK_APPROVED"},
        "confirmation": {"state": "CONFIRMED_" + direction},
        "structure": {"status": "OBSERVED", "regime": regime},
        "strategy_run_provenance": dict(RUN),
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "final_decision": "NO_TRADE",
    }


def fixture(direction="LONG", regime="UPTREND"):
    source_gate = gate(direction, regime)
    context = build_entry_context(
        source="gateio_public_spot", symbol="BTC_USDT",
        candidate_time=NOW, policy_version="test-policy-v1",
        direction=direction, entry=100.0,
        stop=99.0 if direction == "LONG" else 101.0,
        target=103.0 if direction == "LONG" else 97.0,
        gate_evidence=source_gate,
    )
    source_gate["entry_context"] = context
    row = {
        "candidate_event_id": f"hes-v2-candidate-BTC_USDT-15m-{NOW}",
        "candidate_time": NOW, "source": "gateio_public_spot",
        "symbol": "BTC_USDT", "preapproval_paper_eligible": True,
        "entry_context": context, "gate_evidence": source_gate,
    }
    view = {
        "closed_15m_candle_time": NOW,
        "latest_gate_evidence": gate(direction, regime),
    }
    return row, view, context


def test_exact_immutable_setup_context_is_linked_even_if_dashboard_context_is_absent():
    row, view, context = fixture()
    result, reason = resolve_precision_setup_context(
        setup_rows=[row], strategy_view=view, now_s=NOW + 60
    )
    assert result == context
    assert reason == "EXACT_IMMUTABLE_15M_SETUP_LINKED"


def test_context_hash_mismatch_is_rejected():
    row, view, _ = fixture()
    row["entry_context"] = dict(row["entry_context"], target_price=104.0)
    result, reason = resolve_precision_setup_context(
        setup_rows=[row], strategy_view=view, now_s=NOW + 60
    )
    assert result is None
    assert reason.startswith("IMMUTABLE_15M_SETUP_CONTEXT_INVALID:")


def test_setup_from_another_15m_candle_is_not_reused():
    row, view, _ = fixture()
    view["closed_15m_candle_time"] = NOW + 900
    result, reason = resolve_precision_setup_context(
        setup_rows=[row], strategy_view=view, now_s=NOW + 60
    )
    assert result is None
    assert reason == "IMMUTABLE_15M_SETUP_NOT_FOUND"


def test_current_risk_confirmation_and_structure_gates_still_veto():
    for path, value, expected in [
        ("risk", "RISK_REJECTED", "CURRENT_RISK_GATE_NOT_APPROVED"),
        ("confirmation", "UNCONFIRMED", "CURRENT_CONFIRMATION_NOT_VALID"),
        ("structure", "RANGE", "CURRENT_STRUCTURE_NOT_ALIGNED"),
    ]:
        row, view, _ = fixture()
        if path == "structure":
            view["latest_gate_evidence"][path]["regime"] = value
        else:
            view["latest_gate_evidence"][path]["state"] = value
        result, reason = resolve_precision_setup_context(
            setup_rows=[row], strategy_view=view, now_s=NOW + 60
        )
        assert result is None
        assert reason == expected


def test_evaluator_run_change_invalidates_old_setup_context():
    row, view, _ = fixture()
    view["latest_gate_evidence"]["strategy_run_provenance"]["run_id"] = "HESV2-new-run"
    result, reason = resolve_precision_setup_context(
        setup_rows=[row], strategy_view=view, now_s=NOW + 60
    )
    assert result is None
    assert reason == "STRATEGY_RUN_PROVENANCE_MISMATCH"


def test_ambiguous_same_candle_setup_rows_fail_closed():
    row, view, _ = fixture()
    duplicate = dict(row)
    result, reason = resolve_precision_setup_context(
        setup_rows=[row, duplicate], strategy_view=view, now_s=NOW + 60
    )
    assert result is None
    assert reason == "AMBIGUOUS_IMMUTABLE_15M_SETUP"


def test_final_policy_veto_is_not_bypassed_by_preapproval_context():
    row, view, context = fixture()
    row["final_gate_decision"] = "LONG"
    result, reason = resolve_precision_setup_context(
        setup_rows=[row], strategy_view=view, now_s=NOW + 60
    )
    # Preapproval is a paper-only research cohort; this resolver never changes
    # final execution policy and every returned context remains advisory.
    assert result == context
    assert result["execution_enabled"] is False
