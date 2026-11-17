"""Independent, fail-closed confirmation policies for HES strategy families.

Trend delegates to the existing confirmation policy unchanged. Range has a
separate research-only confirmation contract and can never produce the
CONFIRMED_LONG/SHORT states accepted by the shared Risk Gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from .confirmation_engine_v1 import ConfirmationCheck
from .confirmation_policy_v1 import ConfirmationPolicyV1
from .strategy_family_router_v1 import (
    CANONICAL_SOURCE,
    CANONICAL_SYMBOL,
    RANGE_MEAN_REVERSION_RESEARCH_V1,
    SETUP_TIMEFRAME,
    TREND_BREAKOUT_V2,
)

RANGE_REQUIRED_CHECKS = (
    "candidate_valid",
    "range_persistence",
    "range_boundary_location",
    "reversal_trigger",
    "direction_regime_alignment",
    "directional_flow_confirmation",
    "structure_confirmation",
    "cost_adjusted_geometry",
)


@dataclass(frozen=True)
class StrategyFamilyConfirmation:
    family_id: str | None
    family_version: str | None
    state: str
    passed_count: int
    required_count: int
    checks: tuple[ConfirmationCheck, ...]
    reason_codes: tuple[str, ...]
    confirmation_authority: bool = False
    risk_gate_required: bool = True
    candidate_generation_authorized: bool = False
    execution_enabled: bool = False
    orders_placed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "family_version": self.family_version,
            "state": self.state,
            "passed_count": self.passed_count,
            "required_count": self.required_count,
            "checks": [
                {"name": c.name, "state": c.state, "evidence_ref": c.evidence_ref,
                 "observed_at": _utc(c.observed_at).isoformat() if _utc(c.observed_at) else None}
                for c in self.checks
            ],
            "reason_codes": list(self.reason_codes),
            "confirmation_authority": False,
            "risk_gate_required": True,
            "candidate_generation_authorized": False,
            "execution_enabled": False,
            "orders_placed": False,
        }


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _blocked(family_id, family_version, checks, required_count, reason):
    checks = tuple(checks)
    return StrategyFamilyConfirmation(
        family_id, family_version, "UNCONFIRMED",
        sum(isinstance(c, ConfirmationCheck) and c.state == "PASS" for c in checks),
        required_count, checks, (reason,),
    )


def evaluate_strategy_family_confirmation(
    *, route: Mapping[str, Any], candidate: Mapping[str, Any],
    checks: Sequence[ConfirmationCheck], observed_at: datetime,
) -> StrategyFamilyConfirmation:
    """Apply the selected family's independent confirmation contract.

    Candidate and every check must be bound to the same family, 15m setup,
    symbol, direction and UTC observation instant. No result grants risk or
    execution approval. RANGE returns a research-only state by design.
    """
    if not isinstance(route, Mapping) or not isinstance(candidate, Mapping):
        return _blocked(None, None, (), 0, "FAMILY_ROUTE_OR_CANDIDATE_INVALID")
    family_id = route.get("family_id")
    family_version = route.get("family_version")
    if route.get("state") != "FAMILY_IDENTIFIED_NOT_AUTHORIZED":
        return _blocked(family_id, family_version, (), 0, "FAMILY_ROUTE_NOT_VALID")
    if route.get("candidate_generation_authorized") is not False or route.get("execution_enabled") is not False or route.get("orders_placed") is not False:
        return _blocked(family_id, family_version, (), 0, "FAMILY_ROUTE_AUTHORITY_BOUNDARY_VIOLATION")

    profiles = {
        TREND_BREAKOUT_V2.family_id: TREND_BREAKOUT_V2,
        RANGE_MEAN_REVERSION_RESEARCH_V1.family_id: RANGE_MEAN_REVERSION_RESEARCH_V1,
    }
    profile = profiles.get(family_id)
    if profile is None or family_version != profile.version or route.get("activation_state") != profile.activation_state:
        return _blocked(family_id, family_version, (), 0, "FAMILY_PROFILE_VERSION_MISMATCH")

    obs = _utc(observed_at)
    candidate_time = _utc(candidate.get("observed_at"))
    candidate_digest = candidate.get("evidence_sha256")
    digest_valid = (isinstance(candidate_digest, str) and len(candidate_digest) == 64
                    and all(ch in "0123456789abcdef" for ch in candidate_digest.lower()))
    state = candidate.get("state")
    direction = candidate.get("direction")
    expected_direction = {"CANDIDATE_LONG": "LONG", "CANDIDATE_SHORT": "SHORT"}.get(state)
    if (
        obs is None or candidate_time != obs or not digest_valid
        or route.get("symbol") != CANONICAL_SYMBOL or route.get("timeframe") != SETUP_TIMEFRAME
        or candidate.get("source") != CANONICAL_SOURCE
        or candidate.get("family_id") != family_id
        or candidate.get("family_version") != family_version
        or candidate.get("symbol") != route.get("symbol")
        or candidate.get("timeframe") != route.get("timeframe")
        or candidate.get("regime") != route.get("regime")
        or state not in ("CANDIDATE_LONG", "CANDIDATE_SHORT")
        or direction != expected_direction
    ):
        return _blocked(family_id, family_version, (), 0, "FAMILY_CANDIDATE_BINDING_INVALID")
    if family_id == TREND_BREAKOUT_V2.family_id:
        if (candidate.get("regime"), direction) not in (("UPTREND", "LONG"), ("DOWNTREND", "SHORT")):
            return _blocked(family_id, family_version, (), len(ConfirmationPolicyV1.REQUIRED), "TREND_DIRECTION_REGIME_MISMATCH")
        required = tuple(ConfirmationPolicyV1.REQUIRED)
    else:
        if candidate.get("regime") != "RANGE":
            return _blocked(family_id, family_version, (), len(RANGE_REQUIRED_CHECKS), "RANGE_REGIME_MISMATCH")
        required = RANGE_REQUIRED_CHECKS

    if not isinstance(checks, Sequence) or isinstance(checks, (str, bytes)):
        return _blocked(family_id, family_version, (), len(required), "CONFIRMATION_CHECKS_INVALID")
    normalized_checks = tuple(checks)
    if any(not isinstance(c, ConfirmationCheck) for c in normalized_checks):
        return _blocked(family_id, family_version, (), len(required), "CONFIRMATION_CHECK_INVALID")
    names = [c.name for c in normalized_checks]
    if len(names) != len(set(names)):
        return _blocked(family_id, family_version, normalized_checks, len(required), "DUPLICATE_CONFIRMATION_CHECK")
    if any(c.state not in ("PASS", "FAIL", "UNKNOWN") or _utc(c.observed_at) != obs
           or not isinstance(c.evidence_ref, str) or not c.evidence_ref.strip()
           for c in normalized_checks):
        return _blocked(family_id, family_version, normalized_checks, len(required), "CONFIRMATION_EVIDENCE_TIME_OR_STATE_INVALID")
    by_name = {c.name: c for c in normalized_checks}
    missing = tuple(name for name in required if name not in by_name)
    if missing:
        return _blocked(family_id, family_version, normalized_checks, len(required), "MISSING_FAMILY_CONFIRMATION_EVIDENCE:" + ",".join(missing))
    if any(by_name[name].state == "UNKNOWN" for name in required):
        return _blocked(family_id, family_version, normalized_checks, len(required), "UNKNOWN_FAMILY_CONFIRMATION_EVIDENCE")
    if family_id == RANGE_MEAN_REVERSION_RESEARCH_V1.family_id and any(c.state != "PASS" for c in normalized_checks):
        return _blocked(family_id, family_version, normalized_checks, len(required), "RANGE_CONFIRMATION_HAS_NONPASS_EVIDENCE")
    if any(by_name[name].state != "PASS" for name in required):
        return _blocked(family_id, family_version, normalized_checks, len(required), "REQUIRED_FAMILY_CONFIRMATION_FAILED")

    if family_id == TREND_BREAKOUT_V2.family_id:
        # Delegate to the pre-existing Trend policy unchanged.
        result = ConfirmationPolicyV1().evaluate(
            observed_at=obs, candidate=SimpleNamespace(state=state), checks=normalized_checks,
        )
        return StrategyFamilyConfirmation(
            family_id, family_version, result.state, result.passed_count,
            result.required_count, result.checks, result.reason_codes,
        )

    research_state = "RESEARCH_CONFIRMED_LONG" if direction == "LONG" else "RESEARCH_CONFIRMED_SHORT"
    return StrategyFamilyConfirmation(
        family_id, family_version, research_state, len(required), len(required),
        normalized_checks, ("RANGE_RESEARCH_CONFIRMATION_PASSED_RISK_GATE_STILL_REQUIRED",),
    )
