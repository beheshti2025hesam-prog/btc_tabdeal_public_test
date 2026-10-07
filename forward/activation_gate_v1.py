"""Activation gate for forward policies.

A draft or incomplete policy can never silently become an active trading policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ActivationResult:
    active: bool
    errors: tuple[str, ...]


def validate_activation(policy: Mapping[str, Any], ruleset: Mapping[str, Any]) -> ActivationResult:
    errors: list[str] = []

    if policy.get("status") != "ACTIVE":
        errors.append("POLICY_NOT_ACTIVE")
    if ruleset.get("status") != "ACTIVE":
        errors.append("RULESET_NOT_ACTIVE")

    if policy.get("historical_inputs_allowed", False):
        errors.append("HISTORICAL_INPUTS_FORBIDDEN")
    if policy.get("historical_performance_tuning_allowed", False):
        errors.append("HISTORICAL_TUNING_FORBIDDEN")
    if policy.get("future_outcome_leakage_allowed", False):
        errors.append("FUTURE_OUTCOME_LEAKAGE_FORBIDDEN")
    if policy.get("execution_enabled", False):
        errors.append("LIVE_EXECUTION_FORBIDDEN")

    if ruleset.get("historical_inputs_allowed", False):
        errors.append("RULESET_HISTORICAL_INPUTS_FORBIDDEN")
    if ruleset.get("future_outcome_leakage_allowed", False):
        errors.append("RULESET_FUTURE_LEAKAGE_FORBIDDEN")
    if ruleset.get("execution_enabled", False):
        errors.append("RULESET_EXECUTION_FORBIDDEN")

    return ActivationResult(active=not errors, errors=tuple(errors))
