"""Forward-only risk gate primitives.

The gate is intentionally policy-driven. No leverage, sizing, stop distance,
drawdown, RR, or portfolio threshold is hidden in this reference layer.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Sequence

RiskCheckState = Literal["PASS","FAIL","UNKNOWN"]
RiskState = Literal["RISK_APPROVED","RISK_REJECTED"]

@dataclass(frozen=True)
class RiskCheck:
    name: str
    state: RiskCheckState
    evidence_ref: str
    observed_at: object

@dataclass(frozen=True)
class RiskGateResult:
    observed_at: object
    confirmation_state: str
    checks: tuple[RiskCheck, ...]
    state: RiskState
    reason_codes: tuple[str, ...]

class RiskGateV1:
    """Fail-closed boundary; a versioned policy must make risk decisions."""

    def __init__(self, policy=None):
        self.policy = policy

    def evaluate(self, *, observed_at, confirmation, checks: Sequence[RiskCheck] = ()) -> RiskGateResult:
        checks = tuple(checks)
        if self.policy is None:
            return RiskGateResult(
                observed_at=observed_at,
                confirmation_state=getattr(confirmation, "state", "UNKNOWN"),
                checks=checks,
                state="RISK_REJECTED",
                reason_codes=("NO_POLICY_CONFIGURED",),
            )
        result = self.policy.evaluate(
            observed_at=observed_at,
            confirmation=confirmation,
            checks=checks,
        )
        if not isinstance(result, RiskGateResult):
            raise TypeError("Risk policy must return RiskGateResult")
        if any(c.state == "UNKNOWN" for c in result.checks) and result.state == "RISK_APPROVED":
            raise ValueError("UNKNOWN risk check cannot produce approval")
        return result
