"""Adversarial tests for the RiskGateV1 fail-closed boundary."""

from datetime import datetime, timezone

import pytest

from forward.risk_gate_v1 import RiskCheck, RiskGateResult, RiskGateV1
from forward.risk_policy_v1 import RiskPolicyV1

OBS = datetime(2026, 10, 16, tzinfo=timezone.utc)


def _confirmation(state="CONFIRMED_LONG"):
    return type("Confirmation", (), {"state": state})()


def _checks(overrides=None):
    overrides = overrides or {}
    return tuple(
        RiskCheck(
            name,
            overrides.get(name, "PASS"),
            f"evidence:risk:{name}",
            OBS,
        )
        for name in RiskPolicyV1.REQUIRED
    )


class _PermissivePolicy:
    REQUIRED = RiskPolicyV1.REQUIRED

    def __init__(self, checks, confirmation_state="CONFIRMED_LONG"):
        self.checks = tuple(checks)
        self.confirmation_state = confirmation_state

    def evaluate(self, *, observed_at, confirmation, checks=()):
        return RiskGateResult(
            observed_at=observed_at,
            confirmation_state=self.confirmation_state,
            checks=self.checks,
            state="RISK_APPROVED",
            reason_codes=("POLICY_SAYS_APPROVE",),
        )


def _evaluate(policy, confirmation=None):
    return RiskGateV1(policy).evaluate(
        observed_at=OBS,
        confirmation=confirmation or _confirmation(),
        checks=(),
    )


@pytest.mark.parametrize("bad_state", ["FAIL", "UNKNOWN"])
def test_gate_rejects_policy_approval_with_any_non_pass_check(bad_state):
    checks = list(_checks())
    checks[0] = RiskCheck(
        checks[0].name, bad_state, checks[0].evidence_ref, checks[0].observed_at
    )
    result = _evaluate(_PermissivePolicy(checks))
    assert result.state == "RISK_REJECTED"
    assert "NON_PASS_RISK_EVIDENCE" in result.reason_codes


def test_gate_rejects_missing_required_check_even_if_policy_approves():
    result = _evaluate(_PermissivePolicy(_checks()[:-1]))
    assert result.state == "RISK_REJECTED"
    assert "MISSING_RISK_EVIDENCE" in result.reason_codes


def test_gate_rejects_empty_evidence_reference_even_if_policy_approves():
    checks = list(_checks())
    checks[0] = RiskCheck(checks[0].name, "PASS", " ", OBS)
    result = _evaluate(_PermissivePolicy(checks))
    assert result.state == "RISK_REJECTED"
    assert "MALFORMED_RISK_EVIDENCE" in result.reason_codes


def test_gate_rejects_missing_observation_time_even_if_policy_approves():
    checks = list(_checks())
    checks[0] = RiskCheck(checks[0].name, "PASS", checks[0].evidence_ref, None)
    result = _evaluate(_PermissivePolicy(checks))
    assert result.state == "RISK_REJECTED"
    assert "MALFORMED_RISK_EVIDENCE" in result.reason_codes


def test_gate_rejects_duplicate_check_names_even_if_policy_approves():
    checks = list(_checks())
    checks[-1] = checks[0]
    result = _evaluate(_PermissivePolicy(checks))
    assert result.state == "RISK_REJECTED"
    assert "DUPLICATE_RISK_CHECK" in result.reason_codes


def test_gate_rejects_policy_confirmation_state_mismatch():
    result = _evaluate(_PermissivePolicy(_checks(), confirmation_state="CONFIRMED_SHORT"))
    assert result.state == "RISK_REJECTED"
    assert "CONFIRMATION_STATE_MISMATCH" in result.reason_codes


def test_gate_rejects_policy_without_explicit_required_checks():
    class NoDeclaredRequirements:
        def evaluate(self, *, observed_at, confirmation, checks=()):
            return RiskGateResult(
                observed_at, confirmation.state, _checks(),
                "RISK_APPROVED", ("POLICY_SAYS_APPROVE",)
            )

    result = _evaluate(NoDeclaredRequirements())
    assert result.state == "RISK_REJECTED"
    assert "POLICY_REQUIRED_CHECKS_UNDEFINED" in result.reason_codes


def test_reference_policy_approval_survives_gate_validation():
    checks = _checks()
    policy = RiskPolicyV1()
    # The policy is passed the same contemporaneous checks by the gate.
    class PassingPolicy:
        REQUIRED = RiskPolicyV1.REQUIRED

        def evaluate(self, *, observed_at, confirmation, checks=()):
            return policy.evaluate(
                observed_at=observed_at, confirmation=confirmation, checks=checks
            )

    result = RiskGateV1(PassingPolicy()).evaluate(
        observed_at=OBS, confirmation=_confirmation(), checks=checks
    )
    assert result.state == "RISK_APPROVED"


def test_gate_rejects_non_riskcheck_object_even_if_policy_approves():
    result = _evaluate(_PermissivePolicy([object()]))
    assert result.state == "RISK_REJECTED"
    assert "MALFORMED_RISK_EVIDENCE" in result.reason_codes


def test_gate_rejects_invalid_check_state_even_if_policy_approves():
    checks = list(_checks())
    checks[0] = RiskCheck(
        checks[0].name, "PASSED", checks[0].evidence_ref, checks[0].observed_at
    )
    result = _evaluate(_PermissivePolicy(checks))
    assert result.state == "RISK_REJECTED"
    assert "MALFORMED_RISK_EVIDENCE" in result.reason_codes


def test_gate_rejects_duplicate_policy_requirement_names():
    class DuplicateRequirementsPolicy(_PermissivePolicy):
        REQUIRED = (RiskPolicyV1.REQUIRED[0], RiskPolicyV1.REQUIRED[0])

    result = _evaluate(DuplicateRequirementsPolicy(_checks()))
    assert result.state == "RISK_REJECTED"
    assert "POLICY_REQUIRED_CHECKS_UNDEFINED" in result.reason_codes
