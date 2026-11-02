import json

import pytest

from forward.learning_evidence_adapter_v1 import record_signal_decision
from forward.forward_journal_v1 import ForwardJournalV1


def record_decision(path, decision="NO_TRADE", observed_at="2026-10-24T10:00:00+00:00"):
    return record_signal_decision(
        path,
        decision=decision,
        observed_at=observed_at,
        symbol="BTCUSDT",
        timeframe="15m",
        source="gateio_native_ohlcv_v1",
        product="spot",
        response_sha256="a" * 64,
        htf_response_sha256="b" * 64,
        strategy_evidence_sha256="c" * 64,
        policy_version="hes-strategy-policy-v1",
        status="BLOCKED" if decision == "NO_TRADE" else "READY",
        market_regime="UNKNOWN",
        rejected_at="RISK" if decision == "NO_TRADE" else "",
        reason_codes=["RISK_CONTEXT_UNKNOWN"] if decision == "NO_TRADE" else [],
        direction="LONG" if decision == "NO_TRADE" else decision,
        signal_state="CANDIDATE_LONG",
        confirmation_state="CONFIRMED_LONG",
        risk_state="RISK_REJECTED" if decision == "NO_TRADE" else "RISK_APPROVED",
        proposal_decision="CANDIDATE_LONG",
        structure_events=["BOS"],
        structure_labels=["BULLISH_STRUCTURE"],
        confirmation_reasons=["CONFIRMATION_PENDING"],
        risk_reasons=["RISK_CONTEXT_UNKNOWN"],
    )


def test_signal_decision_reuses_canonical_journal_and_is_idempotent(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    first = record_decision(path)
    second = record_decision(path, observed_at="2026-10-24T10:00:15+00:00")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert first.status == "RECORDED"
    assert second.status == "ALREADY_RECORDED"
    assert len(rows) == 1
    assert rows[0]["event_id"] == first.event_id
    assert rows[0]["decision"] == "NO_TRADE"
    assert rows[0]["evidence_source"] == "gateio_native_ohlcv_v1"
    assert rows[0]["risk_state"] == "RISK_REJECTED"
    assert rows[0]["outcome"] is None
    assert rows[0]["closed_at"] is None
    assert rows[0]["execution_enabled"] is False
    assert rows[0]["orders_placed"] is False
    # This exact writer is also used by the existing paper evaluator.
    assert isinstance(ForwardJournalV1(path), ForwardJournalV1)


def test_same_evidence_with_changed_decision_fails_closed(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    record_decision(path, decision="NO_TRADE")
    with pytest.raises(ValueError, match="conflicting_duplicate_decision_event"):
        record_decision(path, decision="SHORT")


def test_signal_decision_preserves_independent_gate_states(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    record_decision(path)
    row = json.loads(path.read_text().splitlines()[0])
    assert row["signal_state"] == "CANDIDATE_LONG"
    assert row["confirmation_state"] == "CONFIRMED_LONG"
    assert row["risk_state"] == "RISK_REJECTED"
    assert row["direction"] == "LONG"
    assert row["proposal_direction"] == "LONG"
    assert row["gate_evidence"]["risk"]["state"] == "RISK_REJECTED"
