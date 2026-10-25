"""Final safety boundary for experimental strategy-policy proposals.

Policy scores are hypotheses, not approval. Until independently validated
structure, confirmation, and risk adapters are configured, directional policy
proposals are downgraded to NO_TRADE. This module never enables execution.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

GATE_VERSION = "hes-strategy-policy-final-gate-v1.0.0"
REQUIRED_UNWIRED_GATES = (
    "MARKET_STRUCTURE_PROVIDER_NOT_WIRED",
    "CONFIRMATION_POLICY_NOT_APPROVED",
    "RISK_GATE_NOT_APPROVED",
)

@dataclass(frozen=True)
class GatedDecision:
    gate_version: str
    proposal: dict[str, Any]
    decision: str
    direction: str
    reasons: tuple[str, ...]
    execution_enabled: bool = False
    orders_placed: bool = False
    def as_dict(self) -> dict[str, Any]:
        return {
            "gate_version": self.gate_version,
            "proposal": self.proposal,
            "decision": self.decision,
            "direction": self.direction,
            "reasons": list(self.reasons),
            "execution_enabled": False,
            "orders_placed": False,
        }

def enforce_final_gates(policy_decision: Any) -> GatedDecision:
    """Preserve the policy output for audit, but fail closed at final boundary."""
    proposal = policy_decision.as_dict()
    if policy_decision.decision in ("LONG", "SHORT"):
        return GatedDecision(GATE_VERSION, proposal, "NO_TRADE", "NONE", REQUIRED_UNWIRED_GATES)
    return GatedDecision(
        GATE_VERSION, proposal, "NO_TRADE", "NONE",
        tuple(policy_decision.reasons) or ("POLICY_PROPOSAL_NOT_ACTIONABLE",),
    )
