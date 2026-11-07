from datetime import datetime, timedelta, timezone

import pytest

from forward.confirmation_engine_v1 import ConfirmationCheck
from forward.risk_gate_v1 import RiskCheck
from forward.signal_agent_v1 import RiskGeometryV1, SignalAgentV1
from forward.strategy_policy_v1 import REQUIRED_CHECKS, StrategyEvidenceCheckV1

OBS = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)


def confirmation_checks(state="PASS", observed_at=OBS):
    names = (
        "structure_direction_aligned",
        "candidate_valid",
        "direction_regime_alignment",
        "structural_event_present",
    )
    return tuple(ConfirmationCheck(n, state, "forward:evidence:" + n, observed_at) for n in names)


def strategy_checks(states=None, observed_at=OBS):
    states = states or {}
    return tuple(
        StrategyEvidenceCheckV1(
            name=name,
            state=states.get(name, "PASS"),
            evidence_ref="forward:strategy:" + name,
            evidence_sha256=f"{index + 1:064x}",
            provider="test-provider",
            provider_version="1",
            observed_at=observed_at,
        )
        for index, name in enumerate(REQUIRED_CHECKS)
    )


def risk_checks(state="PASS", observed_at=OBS):
    names = (
        "confirmation_valid",
        "risk_context_available",
        "entry_stop_target_geometry_valid",
        "risk_reward_gate_passed",
        "execution_disabled",
    )
    return tuple(RiskCheck(n, state, "forward:risk:" + n, observed_at) for n in names)


def evaluate(**kwargs):
    defaults = dict(
        observed_at=OBS,
        venue="gateio",
        product="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        strategy_checks=strategy_checks(),
        regime="UPTREND",
        structure_labels=("HH", "HL"),
        structure_events=("BOS",),
        structure_direction="BULLISH",
        confirmation_checks=confirmation_checks(),
        risk_checks=risk_checks(),
        risk_geometry=RiskGeometryV1(entry="100", stop_loss="97", take_profit="109"),
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
        risk_geometry=RiskGeometryV1(entry="100", stop_loss="103", take_profit="91"),
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


def test_missing_strategy_evidence_fails_closed():
    result = evaluate(strategy_checks=())
    assert result.decision.decision == "NO_TRADE"
    assert any(reason.startswith("MISSING_HTF_TREND_ALIGNMENT") for reason in result.blocked_reasons)


def test_strategy_quorum_failure_fails_closed():
    result = evaluate(strategy_checks=strategy_checks({
        "mfi_confirmation": "FAIL",
        "adx_directional_strength": "FAIL",
    }))
    assert result.decision.decision == "NO_TRADE"
    assert "STRATEGY_CONFIRMATION_QUORUM_NOT_MET" in result.blocked_reasons


def test_caller_cannot_self_assert_strategy_quality():
    checks = confirmation_checks() + (
        ConfirmationCheck("signal_quality_gate_passed", "PASS", "untrusted:caller", OBS),
    )
    result = evaluate(confirmation_checks=checks)
    assert result.decision.decision == "NO_TRADE"
    assert "EXTERNAL_STRATEGY_QUALITY_OVERRIDE_REJECTED" in result.blocked_reasons


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
        ConfirmationCheck(c.name, c.state, "" if c.name == "structure_direction_aligned" else c.evidence_ref, c.observed_at)
        for c in confirmation_checks()
    )
    result = evaluate(confirmation_checks=checks)
    assert result.decision.decision == "NO_TRADE"
    assert "EVIDENCE_REFERENCE_MISSING" in result.blocked_reasons


def test_scope_mismatch_fails_closed():
    result = evaluate(symbol="ETHUSDT")
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


def test_missing_risk_reward_gate_fails_closed():
    checks = tuple(c for c in risk_checks() if c.name != "risk_reward_gate_passed")
    result = evaluate(risk_checks=checks)
    assert result.decision.decision == "NO_TRADE"
    assert result.risk.state == "RISK_REJECTED"
    assert "MISSING_RISK_EVIDENCE" in result.risk.reason_codes


def test_failed_entry_stop_target_geometry_fails_closed():
    checks = tuple(
        RiskCheck(c.name, "FAIL" if c.name == "entry_stop_target_geometry_valid" else c.state,
                  c.evidence_ref, c.observed_at)
        for c in risk_checks()
    )
    result = evaluate(risk_checks=checks)
    assert result.decision.decision == "NO_TRADE"
    assert result.risk.state == "RISK_REJECTED"


def test_missing_execution_disabled_proof_fails_closed():
    checks = tuple(c for c in risk_checks() if c.name != "execution_disabled")
    result = evaluate(risk_checks=checks)
    assert result.decision.decision == "NO_TRADE"
    assert result.risk.state == "RISK_REJECTED"


def test_missing_risk_geometry_fails_closed():
    result = evaluate(risk_geometry=None)
    assert result.decision.decision == "NO_TRADE"
    assert "RISK_GEOMETRY_MISSING" in result.blocked_reasons


def test_reward_risk_below_three_to_one_fails_closed():
    result = evaluate(risk_geometry=RiskGeometryV1(entry="100", stop_loss="97", take_profit="108"))
    assert result.decision.decision == "NO_TRADE"
    assert "RISK_REWARD_BELOW_MINIMUM_3_TO_1" in result.blocked_reasons


def test_long_geometry_with_stop_above_entry_fails_closed():
    result = evaluate(risk_geometry=RiskGeometryV1(entry="100", stop_loss="101", take_profit="110"))
    assert result.decision.decision == "NO_TRADE"
    assert "LONG_RISK_GEOMETRY_ORDER_INVALID" in result.blocked_reasons


def test_short_geometry_with_target_above_entry_fails_closed():
    result = evaluate(
        regime="DOWNTREND",
        structure_labels=("LL", "LH"),
        structure_direction="BEARISH",
        risk_geometry=RiskGeometryV1(entry="100", stop_loss="103", take_profit="101"),
    )
    assert result.decision.decision == "NO_TRADE"
    assert "SHORT_RISK_GEOMETRY_ORDER_INVALID" in result.blocked_reasons


def test_non_finite_risk_geometry_fails_closed():
    result = evaluate(risk_geometry=RiskGeometryV1(entry="NaN", stop_loss="97", take_profit="109"))
    assert result.decision.decision == "NO_TRADE"
    assert "RISK_GEOMETRY_INVALID_NUMBER" in result.blocked_reasons




def test_default_signal_agent_rejects_binance_scope():
    result = evaluate(venue="binance")
    assert result.decision.decision == "NO_TRADE"
    assert "STRATEGY_SCOPE_UNSUPPORTED" in result.blocked_reasons


def test_wrong_market_profile_fails_closed_even_with_strategy_checks():
    result = evaluate(product="usdm_futures")
    assert result.decision.decision == "NO_TRADE"
    assert "STRATEGY_SCOPE_UNSUPPORTED" in result.blocked_reasons


def test_strategy_quality_requires_all_six_measurable_checks():
    result = evaluate(strategy_checks=strategy_checks({"mfi_confirmation": "UNKNOWN"}))
    assert result.decision.decision == "NO_TRADE"
    assert "STRATEGY_EVIDENCE_UNKNOWN" in result.blocked_reasons
