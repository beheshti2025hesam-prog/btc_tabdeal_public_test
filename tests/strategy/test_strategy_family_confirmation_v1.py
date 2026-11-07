from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from forward.confirmation_engine_v1 import ConfirmationCheck
from forward.risk_gate_v1 import RiskGateV1
from forward.risk_policy_v1 import RiskPolicyV1
from forward.strategy_family_confirmation_v1 import (
    RANGE_REQUIRED_CHECKS,
    evaluate_strategy_family_confirmation,
)
from forward.strategy_family_router_v1 import (
    RANGE_MEAN_REVERSION_RESEARCH_V1,
    TREND_BREAKOUT_V2,
    route_strategy_family,
)

OBS = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)


def make_route(family):
    regime = "RANGE" if family == "range_mean_reversion" else "UPTREND"
    return route_strategy_family(
        source="gateio_public_spot", symbol="BTC_USDT", timeframe="15m", regime=regime
    ).as_dict()


def make_candidate(route, direction="LONG"):
    state = "CANDIDATE_LONG" if direction == "LONG" else "CANDIDATE_SHORT"
    return {
        "source": "gateio_public_spot",
        "evidence_sha256": "d" * 64,
        "family_id": route["family_id"],
        "family_version": route["family_version"],
        "state": state,
        "direction": direction,
        "regime": route["regime"],
        "symbol": route["symbol"],
        "timeframe": route["timeframe"],
        "observed_at": OBS,
    }


def make_checks(names):
    return tuple(ConfirmationCheck(n, "PASS", "fixture:" + n, OBS) for n in names)


def test_trend_confirmation_delegates_to_existing_three_check_policy_unchanged():
    route = make_route("trend_breakout")
    result = evaluate_strategy_family_confirmation(
        route=route, candidate=make_candidate(route),
        checks=make_checks(("candidate_valid", "direction_regime_alignment", "structural_event_present")),
        observed_at=OBS,
    )
    assert result.state == "CONFIRMED_LONG"
    assert result.required_count == 3 and result.passed_count == 3
    assert result.confirmation_authority is False
    assert result.risk_gate_required is True
    assert result.execution_enabled is False and result.orders_placed is False


def test_range_has_independent_eight_check_contract_and_research_only_state():
    route = make_route("range_mean_reversion")
    result = evaluate_strategy_family_confirmation(
        route=route, candidate=make_candidate(route, "SHORT"),
        checks=make_checks(RANGE_REQUIRED_CHECKS), observed_at=OBS,
    )
    assert result.state == "RESEARCH_CONFIRMED_SHORT"
    assert result.required_count == 8 and result.passed_count == 8
    assert result.reason_codes == ("RANGE_RESEARCH_CONFIRMATION_PASSED_RISK_GATE_STILL_REQUIRED",)
    assert result.confirmation_authority is False
    assert result.candidate_generation_authorized is False
    assert result.execution_enabled is False and result.orders_placed is False


def test_research_range_confirmation_cannot_pass_shared_risk_gate():
    route = make_route("range_mean_reversion")
    result = evaluate_strategy_family_confirmation(
        route=route, candidate=make_candidate(route),
        checks=make_checks(RANGE_REQUIRED_CHECKS), observed_at=OBS,
    )
    risk = RiskGateV1(RiskPolicyV1()).evaluate(
        observed_at=OBS, confirmation=SimpleNamespace(state=result.state), checks=(),
    )
    assert risk.state == "RISK_REJECTED"
    assert risk.reason_codes == ("CONFIRMATION_NOT_VALID",)


@pytest.mark.parametrize("bad_check", ["range_persistence", "range_boundary_location", "reversal_trigger", "directional_flow_confirmation", "structure_confirmation", "cost_adjusted_geometry"])
def test_range_confirmation_fails_closed_on_any_missing_required_check(bad_check):
    route = make_route("range_mean_reversion")
    names = tuple(n for n in RANGE_REQUIRED_CHECKS if n != bad_check)
    result = evaluate_strategy_family_confirmation(
        route=route, candidate=make_candidate(route), checks=make_checks(names), observed_at=OBS,
    )
    assert result.state == "UNCONFIRMED"
    assert "MISSING_FAMILY_CONFIRMATION_EVIDENCE" in result.reason_codes[0]


def test_range_confirmation_fails_closed_on_unknown_or_failed_evidence():
    route = make_route("range_mean_reversion")
    checks = list(make_checks(RANGE_REQUIRED_CHECKS))
    checks[-1] = ConfirmationCheck(checks[-1].name, "UNKNOWN", "missing", OBS)
    unknown = evaluate_strategy_family_confirmation(route=route, candidate=make_candidate(route), checks=checks, observed_at=OBS)
    assert unknown.state == "UNCONFIRMED"
    checks[-1] = ConfirmationCheck(checks[-1].name, "FAIL", "failed", OBS)
    failed = evaluate_strategy_family_confirmation(route=route, candidate=make_candidate(route), checks=checks, observed_at=OBS)
    assert failed.state == "UNCONFIRMED"


def test_family_confirmation_rejects_spoofed_family_version_or_stale_check():
    route = make_route("range_mean_reversion")
    candidate = make_candidate(route)
    candidate["family_version"] = TREND_BREAKOUT_V2.version
    bad_candidate = evaluate_strategy_family_confirmation(route=route, candidate=candidate, checks=make_checks(RANGE_REQUIRED_CHECKS), observed_at=OBS)
    assert bad_candidate.state == "UNCONFIRMED"
    candidate = make_candidate(route)
    candidate["source"] = "untrusted_source"
    bad_source = evaluate_strategy_family_confirmation(route=route, candidate=candidate, checks=make_checks(RANGE_REQUIRED_CHECKS), observed_at=OBS)
    assert bad_source.state == "UNCONFIRMED"
    candidate = make_candidate(route)
    candidate["evidence_sha256"] = "not-a-digest"
    bad_digest = evaluate_strategy_family_confirmation(route=route, candidate=candidate, checks=make_checks(RANGE_REQUIRED_CHECKS), observed_at=OBS)
    assert bad_digest.state == "UNCONFIRMED"
    candidate = make_candidate(route)
    stale = list(make_checks(RANGE_REQUIRED_CHECKS))
    stale[0] = ConfirmationCheck(stale[0].name, "PASS", "stale", datetime(2026, 11, 7, 19, 59, tzinfo=timezone.utc))
    bad_time = evaluate_strategy_family_confirmation(route=route, candidate=candidate, checks=stale, observed_at=OBS)
    assert bad_time.state == "UNCONFIRMED"


def test_family_confirmation_rejects_duplicate_checks_and_authority_tampering():
    route = make_route("range_mean_reversion")
    checks = make_checks(RANGE_REQUIRED_CHECKS) + (make_checks((RANGE_REQUIRED_CHECKS[0],))[0],)
    duplicate = evaluate_strategy_family_confirmation(route=route, candidate=make_candidate(route), checks=checks, observed_at=OBS)
    assert duplicate.state == "UNCONFIRMED"
    route["execution_enabled"] = True
    tampered = evaluate_strategy_family_confirmation(route=route, candidate=make_candidate(route), checks=make_checks(RANGE_REQUIRED_CHECKS), observed_at=OBS)
    assert tampered.state == "UNCONFIRMED"


def test_invalid_check_objects_fail_closed_without_raising():
    route = make_route("range_mean_reversion")
    result = evaluate_strategy_family_confirmation(route=route, candidate=make_candidate(route), checks=(None,), observed_at=OBS)
    assert result.state == "UNCONFIRMED"
    assert result.reason_codes == ("CONFIRMATION_CHECK_INVALID",)
