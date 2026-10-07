"""Deterministic end-to-end forward safety gate composition."""
from __future__ import annotations
from dataclasses import dataclass
from forward.decision_gate_firewall_v1 import DecisionGateFirewallV1

@dataclass(frozen=True)
class IntegrationGateResult:
    safe: bool
    decision: str
    reason: str

class ForwardIntegrationGateV1:
    def __init__(self) -> None:
        self.firewall = DecisionGateFirewallV1()

    def evaluate(self, *, data_live=True, structure_safe=True, sequence_safe=True,
                 clock_safe=True, health_safe=True, recovery_safe=True,
                 execution_enabled=False, historical_inputs_allowed=False,
                 future_outcomes_allowed=False) -> IntegrationGateResult:
        r = self.firewall.evaluate(
            data_live=data_live, structure_safe=structure_safe,
            sequence_safe=sequence_safe, clock_safe=clock_safe,
            health_safe=health_safe, recovery_safe=recovery_safe,
            execution_enabled=execution_enabled,
            historical_inputs_allowed=historical_inputs_allowed,
            future_outcomes_allowed=future_outcomes_allowed,
        )
        return IntegrationGateResult(r.allowed, r.decision, r.reason)
