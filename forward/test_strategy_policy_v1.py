from datetime import datetime, timedelta, timezone

import pytest

from forward.strategy_policy_v1 import (
    REQUIRED_CHECKS,
    StrategyEvidenceCheckV1,
    StrategyPolicyV1,
)

OBS = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def checks(states=None, observed_at=OBS):
    states = states or {}
    return tuple(
        StrategyEvidenceCheckV1(
            name=name,
            state=states.get(name, "PASS"),
            evidence_ref=f"test-evidence:{name}",
            evidence_sha256=(f"{i + 1:064x}"),
            provider="test-provider",
            provider_version="1",
            observed_at=observed_at,
        )
        for i, name in enumerate(REQUIRED_CHECKS)
    )


def evaluate(evidence=None, **kwargs):
    defaults = dict(
        observed_at=OBS,
        venue="binance",
        product="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        direction="BULLISH",
        checks=checks() if evidence is None else evidence,
    )
    defaults.update(kwargs)
    return StrategyPolicyV1().evaluate(**defaults)


def test_quorum_passes_with_four_market_checks_plus_mandatory_geometry():
    evidence = checks({"mfi_confirmation": "FAIL"})
    result = evaluate(evidence=evidence)
    assert result.state == "PASS"
    assert result.passed_count == 5
    assert result.required_count == 5
    assert result.evidence_sha256 and len(result.evidence_sha256) == 64


def test_quorum_fails_with_only_four_total_passes():
    evidence = checks({
        "mfi_confirmation": "FAIL",
        "adx_directional_strength": "FAIL",
    })
    result = evaluate(evidence=evidence)
    assert result.state == "FAIL"
    assert "STRATEGY_CONFIRMATION_QUORUM_NOT_MET" in result.reason_codes


def test_geometry_is_mandatory_even_when_five_other_checks_pass():
    evidence = checks({"risk_geometry_3_to_1": "FAIL"})
    result = evaluate(evidence=evidence)
    assert result.state == "FAIL"
    assert "MANDATORY_GATE_FAILED:RISK_GEOMETRY_3_TO_1" in result.reason_codes


def test_unknown_check_fails_closed_instead_of_counting_as_a_failed_vote():
    evidence = checks({"mfi_confirmation": "UNKNOWN"})
    result = evaluate(evidence=evidence)
    assert result.state == "UNKNOWN"
    assert "STRATEGY_EVIDENCE_UNKNOWN" in result.reason_codes
    assert result.evidence_sha256 is None


def test_missing_check_fails_closed():
    evidence = tuple(c for c in checks() if c.name != "pullback_location")
    result = evaluate(evidence=evidence)
    assert result.state == "UNKNOWN"
    assert "MISSING_PULLBACK_LOCATION" in result.reason_codes


def test_duplicate_check_fails_closed():
    evidence = checks()
    result = evaluate(evidence=evidence + (evidence[0],))
    assert result.state == "UNKNOWN"
    assert "DUPLICATE_STRATEGY_CHECK" in result.reason_codes


def test_future_evidence_fails_closed():
    evidence = checks(observed_at=OBS + timedelta(seconds=1))
    result = evaluate(evidence=evidence)
    assert result.state == "UNKNOWN"
    assert "FUTURE_STRATEGY_EVIDENCE_REJECTED" in result.reason_codes


def test_bad_hash_fails_closed():
    evidence = list(checks())
    evidence[0] = StrategyEvidenceCheckV1(
        evidence[0].name, evidence[0].state, evidence[0].evidence_ref, "not-a-hash",
        evidence[0].provider, evidence[0].provider_version, evidence[0].observed_at,
    )
    result = evaluate(evidence=tuple(evidence))
    assert result.state == "UNKNOWN"
    assert "STRATEGY_EVIDENCE_HASH_INVALID" in result.reason_codes


@pytest.mark.parametrize("field,value,reason", [
    ("venue", "", "VENUE_MISSING"),
    ("product", "", "PRODUCT_MISSING"),
    ("symbol", "", "SYMBOL_MISSING"),
    ("timeframe", "", "TIMEFRAME_MISSING"),
    ("direction", "UNKNOWN", "DIRECTION_NOT_ESTABLISHED"),
])
def test_missing_or_unknown_scope_fails_closed(field, value, reason):
    result = evaluate(**{field: value})
    assert result.state == "UNKNOWN"
    assert reason in result.reason_codes


def test_evidence_digest_is_deterministic():
    first = evaluate(evidence=checks())
    second = evaluate(evidence=checks())
    assert first.evidence_sha256 == second.evidence_sha256


@pytest.mark.parametrize("mandatory_name", [
    "htf_trend_alignment",
    "pullback_location",
    "reversal_break_confirmation",
    "adx_directional_strength",
    "risk_geometry_3_to_1",
])
def test_core_setup_gate_cannot_be_traded_away_by_five_of_six(mandatory_name):
    result = evaluate(evidence=checks({mandatory_name: "FAIL"}))
    assert result.state == "FAIL"
    assert "MANDATORY_GATE_FAILED:" + mandatory_name.upper() in result.reason_codes


def test_mfi_is_the_only_optional_vote_under_conservative_profile():
    result = evaluate(evidence=checks({"mfi_confirmation": "FAIL"}))
    assert result.state == "PASS"
    assert result.passed_count == 5
