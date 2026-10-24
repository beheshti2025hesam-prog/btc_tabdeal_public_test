from datetime import datetime, timedelta, timezone

import pytest

from forward.confirmation_engine_v1 import ConfirmationCheck
from forward.risk_gate_v1 import RiskCheck
from forward.signal_agent_v1 import SignalAgentV1

OBS = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)


def confirmation_checks(state="PASS", observed_at=OBS):
    names = (
        "structure_direction_aligned",
        "signal_quality_gate_passed",
        "candidate_valid",
        "direction_regime_alignment",
        "structural_event_present",
    )
    return tuple(ConfirmationCheck(n, state, "forward:evidence:" + n, observed_at) for n in names)


def risk_checks(state="PASS", observed_at=OBS):
    names = ("confirmation_valid", "risk_context_available", "execution_disabled")
    return tuple(RiskCheck(n, state, "forward:risk:" + n, observed_at) for n in names)


def evaluate(**kwargs):
    defaults = dict(
        observed_at=OBS,
        symbol="BTC_USDT",
        timeframe="15m",
        regime="UPTREND",
        structure_labels=("HH", "HL"),
        structure_events=("BOS",),
        structure_direction="BULLISH",
        confirmation_checks=confirmation_checks(),
        risk_checks=risk_checks(),
    )
    defaults.update(kwargs)
    return SignalAgentV1().evaluate(**defaults)


def test_full_long_path_requires_all_gates():
    result = evaluate()
    assert result.candidate.state == "CANDIDATE_LONG"
    assert result.confirmation.state == "CONFIRMED_LONG"
    assert result.risk.state == "RISK_APPROVED"
    assert result.decision.decision == "LONG"


def test_full_short_path_is_symmetric():
    result = evaluate(
        regime="DOWNTREND",
        structure_labels=("LL", "LH"),
        structure_direction="BEARISH",
    )
    assert result.candidate.state == "CANDIDATE_SHORT"
    assert result.confirmation.state == "CONFIRMED_SHORT"
    assert result.risk.state == "RISK_APPROVED"
    assert result.decision.decision == "SHORT"


@pytest.mark.parametrize("regime,direction", [
    ("UPTREND", "BEARISH"),
    ("DOWNTREND", "BULLISH"),
    ("RANGE", "BULLISH"),
    ("UNKNOWN", "UNKNOWN"),
])
def test_directional_mismatch_fails_closed(regime, direction):
    result = evaluate(regime=regime, structure_direction=direction)
    assert result.decision.decision == "NO_TRADE"
    assert "STRUCTURE_DIRECTION_NOT_ALIGNED" in result.blocked_reasons


def test_generic_bos_without_direction_is_not_enough():
    result = evaluate(structure_direction="UNKNOWN")
    assert result.decision.decision == "NO_TRADE"


def test_missing_quality_gate_fails_closed():
    checks = tuple(c for c in confirmation_checks() if c.name != "signal_quality_gate_passed")
    result = evaluate(confirmation_checks=checks)
    assert result.decision.decision == "NO_TRADE"
    assert "MISSING_SIGNAL_QUALITY_GATE_PASSED" in result.blocked_reasons


def test_failed_quality_gate_fails_closed():
    checks = tuple(
        ConfirmationCheck(c.name, "FAIL" if c.name == "signal_quality_gate_passed" else c.state,
                          c.evidence_ref, c.observed_at)
        for c in confirmation_checks()
    )
    result = evaluate(confirmation_checks=checks)
    assert result.decision.decision == "NO_TRADE"


def test_unknown_confirmation_evidence_fails_closed():
    result = evaluate(confirmation_checks=confirmation_checks("UNKNOWN"))
    assert result.decision.decision == "NO_TRADE"


def test_missing_confirmation_gate_fails_closed():
    checks = tuple(c for c in confirmation_checks() if c.name != "structural_event_present")
    result = evaluate(confirmation_checks=checks)
    assert result.decision.decision == "NO_TRADE"


def test_risk_veto_blocks_otherwise_confirmed_candidate():
    result = evaluate(risk_checks=risk_checks("FAIL"))
    assert result.confirmation.state == "CONFIRMED_LONG"
    assert result.risk.state == "RISK_REJECTED"
    assert result.decision.decision == "NO_TRADE"


def test_unknown_risk_context_fails_closed():
    result = evaluate(risk_checks=risk_checks("UNKNOWN"))
    assert result.risk.state == "RISK_REJECTED"
    assert result.decision.decision == "NO_TRADE"


def test_future_confirmation_evidence_is_rejected():
    future = confirmation_checks(observed_at=OBS + timedelta(seconds=1))
    result = evaluate(confirmation_checks=future)
    assert result.decision.decision == "NO_TRADE"
    assert "FUTURE_EVIDENCE_REJECTED" in result.blocked_reasons


def test_naive_evidence_timestamp_is_rejected():
    naive = confirmation_checks(observed_at=datetime(2026, 10, 24, 10, 0))
    result = evaluate(confirmation_checks=naive)
    assert result.decision.decision == "NO_TRADE"
    assert "EVIDENCE_TIMESTAMP_INVALID" in result.blocked_reasons


def test_missing_evidence_reference_is_rejected():
    checks = tuple(
        ConfirmationCheck(c.name, c.state, "" if c.name == "signal_quality_gate_passed" else c.evidence_ref, c.observed_at)
        for c in confirmation_checks()
    )
    result = evaluate(confirmation_checks=checks)
    assert result.decision.decision == "NO_TRADE"
    assert "EVIDENCE_REFERENCE_MISSING" in result.blocked_reasons


def test_scope_mismatch_fails_closed():
    result = evaluate(symbol="ETH_USDT")
    assert result.decision.decision == "NO_TRADE"


def test_no_structural_event_fails_closed():
    result = evaluate(structure_events=())
    assert result.decision.decision == "NO_TRADE"


def test_unconfirmed_candidate_never_becomes_trade():
    result = evaluate(confirmation_checks=confirmation_checks("FAIL"))
    assert result.decision.decision == "NO_TRADE"


def test_execution_is_never_enabled_by_signal_agent():
    result = evaluate()
    assert result.decision.decision == "LONG"
    assert "execution_disabled" in {c.name for c in result.risk.checks}


def test_duplicate_evidence_names_fail_closed():
    checks = confirmation_checks() + (confirmation_checks()[0],)
    result = evaluate(confirmation_checks=checks)
    assert result.decision.decision == "NO_TRADE"
    assert "DUPLICATE_EVIDENCE_CHECK_NAME" in result.blocked_reasons
