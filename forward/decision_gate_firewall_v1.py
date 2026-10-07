"""Final fail-closed firewall before any forward decision."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class GateResult:
    allowed: bool
    decision: str
    reason: str

class DecisionGateFirewallV1:
    """Allows a decision only when every mandatory safety condition is explicitly true."""
    def evaluate(self, *, data_live: bool, structure_safe: bool, sequence_safe: bool,
                 clock_safe: bool, health_safe: bool, recovery_safe: bool,
                 execution_enabled: bool = False, historical_inputs_allowed: bool = False,
                 future_outcomes_allowed: bool = False) -> GateResult:
        checks = {
            "DATA_NOT_LIVE": data_live,
            "STRUCTURE_UNSAFE": structure_safe,
            "SEQUENCE_UNSAFE": sequence_safe,
            "CLOCK_UNSAFE": clock_safe,
            "HEALTH_UNSAFE": health_safe,
            "RECOVERY_UNSAFE": recovery_safe,
            "EXECUTION_ENABLED": not execution_enabled,
            "HISTORICAL_INPUT": not historical_inputs_allowed,
            "FUTURE_OUTCOME": not future_outcomes_allowed,
        }
        for reason, ok in checks.items():
            if not ok:
                return GateResult(False, "NO_TRADE", reason)
        return GateResult(True, "NO_TRADE", "OBSERVATION_ONLY_NO_EXECUTION")
