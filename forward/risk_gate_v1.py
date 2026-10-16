"""Forward-only risk gate primitives.

The gate is intentionally policy-driven. No leverage, sizing, stop distance,
drawdown, RR, or portfolio threshold is hidden in this reference layer.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Sequence

RiskCheckState = Literal["PASS", "FAIL", "UNKNOWN"]
RiskState = Literal["RISK_APPROVED", "RISK_REJECTED"]
_VALID_CHECK_STATES = frozenset(("PASS", "FAIL", "UNKNOWN"))


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
        confirmation_state = getattr(confirmation, "state", "UNKNOWN")

        def reject(*reason_codes, result_checks=None):
            selected_checks = checks if result_checks is None else result_checks
            try:
                safe_checks = tuple(selected_checks)
            except TypeError:
                safe_checks = checks
            return RiskGateResult(
                observed_at=observed_at,
                confirmation_state=confirmation_state,
                checks=safe_checks,
                state="RISK_REJECTED",
                reason_codes=tuple(reason_codes),
            )

        if self.policy is None:
            return reject("NO_POLICY_CONFIGURED")

        result = self.policy.evaluate(
            observed_at=observed_at,
            confirmation=confirmation,
            checks=checks,
        )
        if not isinstance(result, RiskGateResult):
            raise TypeError("Risk policy must return RiskGateResult")
        if result.state not in ("RISK_APPROVED", "RISK_REJECTED"):
            return reject("INVALID_POLICY_RESULT_STATE")
        if result.confirmation_state != confirmation_state:
            return reject("CONFIRMATION_STATE_MISMATCH", result_checks=result.checks)
        if result.state == "RISK_REJECTED":
            return result
        if confirmation_state not in ("CONFIRMED_LONG", "CONFIRMED_SHORT"):
            return reject("CONFIRMATION_NOT_VALID", result_checks=result.checks)
        if result.observed_at is None:
            return reject("MALFORMED_POLICY_RESULT", result_checks=result.checks)
        if result.observed_at != observed_at:
            return reject("OBSERVATION_TIME_MISMATCH", result_checks=result.checks)
        if (
            not isinstance(result.reason_codes, (tuple, list))
            or not result.reason_codes
            or any(not isinstance(code, str) or not code.strip() for code in result.reason_codes)
        ):
            return reject("MALFORMED_POLICY_RESULT", result_checks=result.checks)

        # Defense in depth: approval requires an explicit versioned required-check
        # list and a complete, well-formed, all-PASS result. A policy's own
        # approval is not sufficient evidence by itself.
        required = getattr(self.policy, "REQUIRED", None)
        if (
            not isinstance(required, (tuple, list))
            or not required
            or any(not isinstance(name, str) or not name.strip() for name in required)
            or len(set(required)) != len(required)
        ):
            return reject("POLICY_REQUIRED_CHECKS_UNDEFINED", result_checks=result.checks)

        try:
            result_checks = tuple(result.checks)
        except TypeError:
            return reject("MALFORMED_RISK_EVIDENCE")
        by_name = {}
        for check in result_checks:
            if not isinstance(check, RiskCheck):
                return reject("MALFORMED_RISK_EVIDENCE", result_checks=result_checks)
            if (
                not isinstance(check.name, str)
                or not check.name.strip()
                or not isinstance(check.state, str)
                or check.state not in _VALID_CHECK_STATES
                or not isinstance(check.evidence_ref, str)
                or not check.evidence_ref.strip()
                or check.observed_at is None
            ):
                return reject("MALFORMED_RISK_EVIDENCE", result_checks=result_checks)
            if check.name in by_name:
                return reject("DUPLICATE_RISK_CHECK", result_checks=result_checks)
            by_name[check.name] = check

        missing = tuple(name for name in required if name not in by_name)
        if missing:
            return reject(
                "MISSING_RISK_EVIDENCE",
                *(f"MISSING:{name}" for name in missing),
                result_checks=result_checks,
            )
        if any(check.state != "PASS" for check in result_checks):
            return reject("NON_PASS_RISK_EVIDENCE", result_checks=result_checks)

        return result
