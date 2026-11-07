"""Final fail-closed firewall before any forward decision."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    decision: str
    reason: str


class DecisionGateFirewallV1:
    """Allows an observation only when every safety input has the exact required bool value."""

    def evaluate(
        self,
        *,
        data_live: bool,
        structure_safe: bool,
        sequence_safe: bool,
        clock_safe: bool,
        health_safe: bool,
        recovery_safe: bool,
        execution_enabled: bool = False,
        historical_inputs_allowed: bool = False,
        future_outcomes_allowed: bool = False,
    ) -> GateResult:
        checks = {
            "DATA_NOT_LIVE": data_live is True,
            "STRUCTURE_UNSAFE": structure_safe is True,
            "SEQUENCE_UNSAFE": sequence_safe is True,
            "CLOCK_UNSAFE": clock_safe is True,
            "HEALTH_UNSAFE": health_safe is True,
            "RECOVERY_UNSAFE": recovery_safe is True,
            "EXECUTION_ENABLED": execution_enabled is False,
            "HISTORICAL_INPUT": historical_inputs_allowed is False,
            "FUTURE_OUTCOME": future_outcomes_allowed is False,
        }
        for reason, ok in checks.items():
            if not ok:
                return GateResult(False, "NO_TRADE", reason)
        return GateResult(True, "NO_TRADE", "OBSERVATION_ONLY_NO_EXECUTION")
