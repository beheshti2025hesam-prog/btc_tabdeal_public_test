from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from forward.learning_evidence_adapter_v1 import record_signal_decision
from forward.trade_journal_view_v1 import JournalProjectionError, read_decision_journal


def write_signal(path, *, observed_at=None):
    return record_signal_decision(
        path,
        decision="NO_TRADE",
        observed_at=observed_at or datetime.now(timezone.utc).isoformat(),
        symbol="BTCUSDT",
        timeframe="15m",
        source="gateio_native_ohlcv_v1",
        product="spot",
        response_sha256="a" * 64,
        htf_response_sha256="b" * 64,
        strategy_evidence_sha256="c" * 64,
        policy_version="hes-strategy-policy-v1",
        status="BLOCKED",
        market_regime="UNKNOWN",
        rejected_at="RISK",
        reason_codes=["RISK_CONTEXT_UNKNOWN"],
        risk_state="RISK_REJECTED",
    )


def test_projects_canonical_signal_and_paper_decisions_without_inventing_outcomes(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "schema": "hes_trade_journal_paper_candidate_v1",
            "event_id": "paper-candidate-1", "observed_at": datetime.now(timezone.utc).isoformat(),
            "symbol": "BTCUSDT", "timeframe": "15m", "decision": "PAPER_CANDIDATE",
            "outcome": None, "execution_enabled": False, "orders_placed": False,
        }) + "\n")
    result = read_decision_journal(path)
    assert result["status"] == "VERIFIED"
    assert result["count"] == 2
    assert result["decision_count"] == 1
    event = result["events"][0]
    assert event["decision"] == "NO_TRADE"
    assert event["realized_outcome"] == "NOT_LINKED"
    assert event["execution"] == "OFF"
    assert event["reason_codes"] == ["RISK_CONTEXT_UNKNOWN"]


def test_rejects_tampered_json_and_duplicate_event_identity(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    line = path.read_text()
    path.write_text(line + line)
    with pytest.raises(JournalProjectionError, match="duplicate_event"):
        read_decision_journal(path)


def test_rejects_partial_trailing_record(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    with pytest.raises(JournalProjectionError, match="partial_trailing_record"):
        read_decision_journal(path)


def test_rejects_naive_timestamp(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    record = json.loads(path.read_text().strip())
    record["observed_at"] = "2026-10-25T10:00:00"
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(JournalProjectionError, match="naive_timestamp"):
        read_decision_journal(path)


def test_rejects_outcome_leakage_in_decision_record(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    record = json.loads(path.read_text().strip())
    record["outcome"] = "WIN"
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(JournalProjectionError, match="outcome_leakage"):
        read_decision_journal(path)


def test_optional_canonical_identity_and_execution_contract(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    with pytest.raises(JournalProjectionError, match="unexpected_source"):
        read_decision_journal(path, expected_source="gateio_public_spot")
def test_rejects_invalid_limit(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    write_signal(path)
    with pytest.raises(JournalProjectionError, match="invalid_limit"):
        read_decision_journal(path, limit=0)



def _write_v2_decision(path, *, proposal_decision="NO_TRADE", confirmation_state="UNCONFIRMED",
                       risk_state="RISK_REJECTED", final_decision="NO_TRADE"):
    route = {
        "family_id": "trend_breakout",
        "family_version": "hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
        "activation_state": "CANDIDATE_LOCKED_NOT_ACTIVE",
    }
    evidence = {
        "confirmation": {
            "state": confirmation_state,
            "reason_codes": ["REQUIRED_CHECK_FAILED"] if confirmation_state == "UNCONFIRMED" else [],
            "checks": [{"name": "direction_regime_alignment", "state": "FAIL" if confirmation_state == "UNCONFIRMED" else "PASS"}],
        },
        "risk": {
            "state": risk_state,
            "reason_codes": ["CONFIRMATION_NOT_VALID"] if risk_state == "RISK_REJECTED" else [],
            "checks": [{"name": "confirmation_valid", "state": "FAIL" if risk_state == "RISK_REJECTED" else "PASS"}],
        },
    }
    record = {
        "event_id": "hes-v2-attribution-test",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "decision": final_decision,
        "direction": "NONE",
        "signal_state": proposal_decision,
        "proposal_decision": proposal_decision,
        "proposal_reasons": ["NO_CONFIRMED_20_BAR_BREAKOUT"] if proposal_decision == "NO_TRADE" else [],
        "confirmation_state": confirmation_state,
        "risk_state": risk_state,
        "no_trade_reason": "NO_CONFIRMED_20_BAR_BREAKOUT" if proposal_decision == "NO_TRADE" else "GATE_REJECTED",
        "gate_reasons": ["NO_CONFIRMED_20_BAR_BREAKOUT"] if proposal_decision == "NO_TRADE" else ["GATE_REJECTED"],
        "gate_evidence": evidence,
        "strategy_family_route": route,
        "strategy_family_context_status": "VERIFIED_EVIDENCE_ONLY_NOT_AUTHORIZED",
        "market_data_provenance": {
            "timeframes": {"15m": {"input_batch_sha256": "a" * 64}, "1h": {"input_batch_sha256": "b" * 64}},
        },
        "strategy_run_provenance": {
            "code_release_id": "release-sha",
            "run_id": "run-123",
            "run_manifest_sha256": "c" * 64,
        },
        "evidence_source": "gateio_public_spot",
        "execution_enabled": False,
        "orders_placed": False,
        "outcome": None,
        "closed_at": None,
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_projects_strategy_family_gate_attribution_and_provenance(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    _write_v2_decision(path)
    event = read_decision_journal(path)["events"][0]
    assert event["decision_gate"] == "STRATEGY_POLICY"
    assert event["rejected_at"] == "STRATEGY_POLICY"
    assert event["reason_codes"] == ["NO_CONFIRMED_20_BAR_BREAKOUT"]
    assert event["strategy_family_id"] == "trend_breakout"
    assert event["strategy_family_version"] == "hes-btcusdt-mtf-confirmed-breakout-v2.0.0"
    assert event["strategy_family_activation_state"] == "CANDIDATE_LOCKED_NOT_ACTIVE"
    assert event["strategy_family_context_status"] == "VERIFIED_EVIDENCE_ONLY_NOT_AUTHORIZED"
    assert event["market_data_batch_sha256_by_timeframe"] == {"15m": "a" * 64, "1h": "b" * 64}
    assert event["code_release_id"] == "release-sha"
    assert event["run_id"] == "run-123"
    assert event["run_manifest_sha256"] == "c" * 64
    assert event["gate_summary"]["confirmation"]["failed_checks"] == ["direction_regime_alignment"]
    assert event["gate_summary"]["risk"]["failed_checks"] == ["confirmation_valid"]


def test_rejection_stage_uses_confirmation_then_risk_then_final_policy(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    _write_v2_decision(path, proposal_decision="LONG", confirmation_state="UNCONFIRMED", risk_state="RISK_REJECTED")
    assert read_decision_journal(path)["events"][0]["rejected_at"] == "CONFIRMATION"

    _write_v2_decision(path, proposal_decision="LONG", confirmation_state="CONFIRMED_LONG", risk_state="RISK_REJECTED")
    assert read_decision_journal(path)["events"][0]["rejected_at"] == "RISK"

    _write_v2_decision(path, proposal_decision="LONG", confirmation_state="CONFIRMED_LONG", risk_state="RISK_APPROVED")
    assert read_decision_journal(path)["events"][0]["rejected_at"] == "FINAL_POLICY"


def test_missing_gate_evidence_is_not_given_invented_attribution(tmp_path):
    path = tmp_path / "trade_journal_v2.jsonl"
    record = {
        "event_id": "legacy-no-trade",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "decision": "NO_TRADE",
        "evidence_source": "gateio_public_spot",
        "execution_enabled": False,
        "orders_placed": False,
        "outcome": None,
        "closed_at": None,
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    event = read_decision_journal(path)["events"][0]
    assert event["decision_gate"] == "UNKNOWN"
    assert event["rejected_at"] == "UNKNOWN"
