"""Fail-closed validator for explicit forward policies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class PolicyValidationResult:
    valid: bool
    errors: tuple[str, ...]


REQUIRED = (
    "policy_id",
    "version",
    "effective_from",
    "market_scope",
    "market_structure",
    "opportunity",
    "confirmation",
    "risk",
    "decision",
    "quality_policy",
    "no_trade_policy",
)


def validate_forward_policy(policy: Mapping[str, Any]) -> PolicyValidationResult:
    errors: list[str] = []

    for key in REQUIRED:
        if key not in policy:
            errors.append(f"MISSING:{key}")

    if policy.get("historical_inputs_allowed", False):
        errors.append("HISTORICAL_INPUTS_FORBIDDEN")
    if policy.get("historical_performance_tuning_allowed", False):
        errors.append("HISTORICAL_TUNING_FORBIDDEN")
    if policy.get("future_outcome_leakage_allowed", False):
        errors.append("FUTURE_OUTCOME_LEAKAGE_FORBIDDEN")
    if policy.get("long_short_symmetry_required") is not True:
        errors.append("LONG_SHORT_SYMMETRY_REQUIRED")
    if policy.get("fail_closed") is not True:
        errors.append("FAIL_CLOSED_REQUIRED")
    if policy.get("execution_enabled", False):
        errors.append("LIVE_EXECUTION_FORBIDDEN")

    for section in ("market_structure", "opportunity", "confirmation", "risk", "decision"):
        value = policy.get(section)
        if isinstance(value, Mapping) and value.get("status") == "NOT_CONFIGURED":
            errors.append(f"UNCONFIGURED:{section}")

    return PolicyValidationResult(valid=not errors, errors=tuple(errors))
