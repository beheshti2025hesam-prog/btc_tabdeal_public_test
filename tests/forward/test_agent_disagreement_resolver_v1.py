from datetime import datetime, timezone, timedelta
from hashlib import sha256

import pytest

from forward.agent_disagreement_resolver_v1 import AgentAssessmentV1, AgentDisagreementResolverV1


NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
SNAP = sha256(b"snapshot").hexdigest()


def assessment(agent, direction="LONG", state="PASS", **kw):
    return AgentAssessmentV1(
        agent_id=agent, agent_version="test-v1", state=state, direction=direction,
        venue=kw.get("venue", "binance"), product=kw.get("product", "spot"),
        symbol=kw.get("symbol", "BTCUSDT"), timeframe=kw.get("timeframe", "15m"),
        as_of=kw.get("as_of", NOW), snapshot_sha256=kw.get("snapshot", SNAP),
        evidence_sha256=kw.get("evidence", sha256(agent.encode()).hexdigest()),
        reason_codes=kw.get("reasons", ()),
    )


def group(**overrides):
    agents = {
        "data_quality": assessment("data_quality"),
        "market_structure": assessment("market_structure"),
        "strategy": assessment("strategy"),
        "confirmation": assessment("confirmation"),
        "risk": assessment("risk"),
    }
    agents.update(overrides)
    return tuple(agents.values())


def test_consistent_same_snapshot_assessments_pass_deterministically():
    resolver = AgentDisagreementResolverV1()
    result = resolver.resolve(assessments=group(), observed_at=NOW)
    again = resolver.resolve(assessments=group(), observed_at=NOW)
    assert (result.decision, result.direction, result.conflict_class) == ("LONG", "LONG", "CONSENSUS")
    assert result.audit_sha256 == again.audit_sha256


def test_opposing_long_short_is_no_trade():
    items = list(group())
    items[1] = assessment("market_structure", direction="SHORT")
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "DIRECTION_CONFLICT"


@pytest.mark.parametrize("change,expected", [
    ({"snapshot": sha256(b"other").hexdigest()}, "SNAPSHOT_MISMATCH"),
    ({"as_of": NOW - timedelta(minutes=1)}, "AS_OF_MISMATCH"),
    ({"symbol": "ETHUSDT"}, "SCOPE_MISMATCH"),
])
def test_mismatched_scope_or_evidence_is_rejected(change, expected):
    items = list(group())
    items[1] = assessment("market_structure", **change)
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == expected


def test_risk_veto_beats_majority():
    items = list(group())
    items[4] = assessment("risk", state="FAIL")
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "MANDATORY_VETO"


def test_unknown_is_not_a_vote_or_pass():
    items = list(group())
    items[2] = assessment("strategy", state="UNKNOWN")
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "UNKNOWN_EVIDENCE"


def test_duplicate_agent_reports_are_rejected():
    items = list(group()) + [assessment("risk")]
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "DUPLICATE_REPORT"


def test_future_timestamp_is_rejected():
    items = list(group())
    items[0] = assessment("data_quality", as_of=NOW + timedelta(seconds=1))
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "FUTURE_EVIDENCE"


def test_missing_required_agent_is_rejected():
    result = AgentDisagreementResolverV1().resolve(assessments=group()[:-1], observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "MISSING_REQUIRED_AGENT"


def test_invalid_naive_timestamp_fails_closed():
    items = list(group())
    items[0] = assessment("data_quality", as_of=datetime(2026, 10, 24, 12))
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "INVALID_TIMESTAMP"


def test_caller_cannot_remove_core_mandatory_agents():
    result = AgentDisagreementResolverV1().resolve(
        assessments=(assessment("market_structure"),),
        observed_at=NOW,
        required_agents=(),
    )
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "MISSING_REQUIRED_AGENT"
    assert "MISSING_REQUIRED_AGENT:risk" in result.reason_codes


def test_strategy_and_confirmation_must_both_supply_directional_votes():
    items = list(group())
    items[1] = assessment("market_structure", direction="LONG")
    items[2] = assessment("strategy", direction="NEUTRAL")
    items[3] = assessment("confirmation", direction="NEUTRAL")
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "INSUFFICIENT_DIRECTIONAL_QUORUM"
    assert "DIRECTIONAL_QUORUM_NOT_MET:strategy" in result.reason_codes
    assert "DIRECTIONAL_QUORUM_NOT_MET:confirmation" in result.reason_codes


def test_neutral_market_structure_can_support_an_aligned_strategy_confirmation_pair():
    items = (
        assessment("data_quality", direction="NEUTRAL"),
        assessment("market_structure", direction="NEUTRAL"),
        assessment("strategy", direction="LONG"),
        assessment("confirmation", direction="LONG"),
        assessment("risk", direction="NEUTRAL"),
    )
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert (result.decision, result.direction, result.conflict_class) == ("LONG", "LONG", "CONSENSUS")


def test_all_assessments_must_bind_to_the_supplied_observation_time():
    stale = NOW - timedelta(minutes=5)
    items = tuple(assessment(name, as_of=stale) for name in
                  ("data_quality", "market_structure", "strategy", "confirmation", "risk"))
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "AS_OF_MISMATCH"


def test_invalid_observation_time_fails_closed():
    result = AgentDisagreementResolverV1().resolve(
        assessments=group(),
        observed_at=datetime(2026, 10, 24, 12),
    )
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "INVALID_TIMESTAMP"


def test_malformed_reason_codes_are_rejected_not_stringified():
    items = list(group())
    items[2] = assessment("strategy", reasons=("OK", object()))
    result = AgentDisagreementResolverV1().resolve(assessments=items, observed_at=NOW)
    assert result.decision == "NO_TRADE"
    assert result.conflict_class == "INVALID_REASON_CODES"
