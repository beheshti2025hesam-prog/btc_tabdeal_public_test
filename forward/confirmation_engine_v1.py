"""Forward-only confirmation/confluence primitives.

This module evaluates a supplied, versioned confirmation policy. It does not
invent thresholds, weights, indicators, or historical optimization targets.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Sequence

CheckState = Literal["PASS","FAIL","UNKNOWN"]
ConfirmationState = Literal["CONFIRMED_LONG","CONFIRMED_SHORT","UNCONFIRMED"]

@dataclass(frozen=True)
class ConfirmationCheck:
    name: str
    state: CheckState
    evidence_ref: str
    observed_at: object

@dataclass(frozen=True)
class ConfirmationResult:
    observed_at: object
    candidate_state: str
    checks: tuple[ConfirmationCheck, ...]
    passed_count: int
    required_count: int
    state: ConfirmationState
    reason_codes: tuple[str, ...]

class ConfirmationEngineV1:
    """Fail-closed contract boundary; policy is explicitly supplied."""

    def __init__(self, policy=None):
        self.policy = policy

    def evaluate(self, *, observed_at, candidate, checks: Sequence[ConfirmationCheck] = ()) -> ConfirmationResult:
        checks = tuple(checks)
        if self.policy is None:
            return ConfirmationResult(
                observed_at=observed_at,
                candidate_state=getattr(candidate, "state", "UNKNOWN"),
                checks=checks,
                passed_count=sum(c.state == "PASS" for c in checks),
                required_count=0,
                state="UNCONFIRMED",
                reason_codes=("NO_POLICY_CONFIGURED",),
            )
        result = self.policy.evaluate(observed_at=observed_at, candidate=candidate, checks=checks)
        if not isinstance(result, ConfirmationResult):
            raise TypeError("Confirmation policy must return ConfirmationResult")
        if any(c.state == "UNKNOWN" for c in result.checks) and result.state != "UNCONFIRMED":
            raise ValueError("UNKNOWN confirmation check cannot produce a confirmed state")
        return result
