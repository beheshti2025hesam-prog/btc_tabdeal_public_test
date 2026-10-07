"""Integration boundary: RiskGate -> DecisionEngine -> Decision Journal."""

from datetime import datetime, timezone
import json

from forward.decision_engine_v1 import DecisionEngineV1
from forward.forward_journal_v1 import ForwardJournalV1
from forward.risk_gate_v1 import RiskCheck, RiskGateV1
from forward.risk_policy_v1 import RiskPolicyV1

OBS = datetime(2026, 10, 7, tzinfo=timezone.utc)


def _confirmation(state):
    return type("Confirmation", (), {"state": state})()


def _candidate(state):
    return type("Candidate", (), {"state": state})()


def _checks(state="PASS"):
    return tuple(
        RiskCheck(name, state, "forward:risk:" + name, OBS)
        for name in RiskPolicyV1.REQUIRED
    )


def _journal_record(result):
    return {
        "event_id": "evt-risk-gate-e2e-001",
        "observed_at": result.observed_at.isoformat(),
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "decision": result.decision,
        "evidence_source": ["live-observation-risk-gate-001"],
        "reason_codes": list(result.reason_codes),
    }


def test_real_risk_gate_reject_to_no_trade_to_journal(tmp_path):
    confirmation = _confirmation("CONFIRMED_LONG")
    risk = RiskGateV1(RiskPolicyV1()).evaluate(
        observed_at=OBS,
        confirmation=confirmation,
        checks=_checks("FAIL"),
    )
    decision = DecisionEngineV1().evaluate(
        observed_at=OBS,
        candidate=_candidate("CANDIDATE_LONG"),
        confirmation=confirmation,
        risk=risk,
    )

    assert risk.state == "RISK_REJECTED"
    assert decision.decision == "NO_TRADE"

    journal = ForwardJournalV1(tmp_path / "journal.jsonl")
    journal.append_decision(_journal_record(decision))

    stored = json.loads(
        (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert stored["decision"] == "NO_TRADE"
    assert stored["outcome"] is None
    assert stored["closed_at"] is None


def test_real_risk_gate_fail_closed_without_policy():
    confirmation = _confirmation("CONFIRMED_SHORT")
    risk = RiskGateV1().evaluate(
        observed_at=OBS,
        confirmation=confirmation,
        checks=(),
    )
    decision = DecisionEngineV1().evaluate(
        observed_at=OBS,
        candidate=_candidate("CANDIDATE_SHORT"),
        confirmation=confirmation,
        risk=risk,
    )

    assert risk.state == "RISK_REJECTED"
    assert "NO_POLICY_CONFIGURED" in risk.reason_codes
    assert decision.decision == "NO_TRADE"


def test_long_requires_all_three_gates():
    confirmation = _confirmation("CONFIRMED_LONG")
    risk = RiskGateV1(RiskPolicyV1()).evaluate(
        observed_at=OBS,
        confirmation=confirmation,
        checks=_checks(),
    )
    result = DecisionEngineV1().evaluate(
        observed_at=OBS,
        candidate=_candidate("CANDIDATE_LONG"),
        confirmation=confirmation,
        risk=risk,
    )
    assert risk.state == "RISK_APPROVED"
    assert result.decision == "LONG"


def test_short_requires_directional_alignment():
    confirmation = _confirmation("CONFIRMED_SHORT")
    risk = RiskGateV1(RiskPolicyV1()).evaluate(
        observed_at=OBS,
        confirmation=confirmation,
        checks=_checks(),
    )
    result = DecisionEngineV1().evaluate(
        observed_at=OBS,
        candidate=_candidate("CANDIDATE_SHORT"),
        confirmation=confirmation,
        risk=risk,
    )
    assert risk.state == "RISK_APPROVED"
    assert result.decision == "SHORT"
