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

def enforce_final_gates(policy_decision: Any, gate_evidence: dict[str, Any] | None = None) -> GatedDecision:
    """Preserve the policy output for audit, but fail closed at final boundary."""
    proposal = policy_decision.as_dict()
    if policy_decision.decision in ("LONG", "SHORT"):
        if gate_evidence is None:
            reasons = REQUIRED_UNWIRED_GATES
        else:
            reasons_list = []
            structure = gate_evidence.get("structure", {})
            confirmation = gate_evidence.get("confirmation", {})
            risk = gate_evidence.get("risk", {})
            if structure.get("status") != "OBSERVED" or structure.get("regime") == "UNKNOWN":
                reasons_list.append("MARKET_STRUCTURE_UNKNOWN_OR_INSUFFICIENT")
            if confirmation.get("state") not in ("CONFIRMED_LONG", "CONFIRMED_SHORT"):
                reasons_list.extend(confirmation.get("reason_codes") or ["CONFIRMATION_NOT_APPROVED"])
            if risk.get("state") != "RISK_APPROVED":
                reasons_list.extend(risk.get("reason_codes") or ["RISK_GATE_NOT_APPROVED"])
            reasons = tuple(dict.fromkeys(reasons_list)) or ("FINAL_POLICY_APPROVAL_REQUIRED",)
        return GatedDecision(GATE_VERSION, proposal, "NO_TRADE", "NONE", reasons)
    return GatedDecision(
        GATE_VERSION, proposal, "NO_TRADE", "NONE",
        tuple(policy_decision.reasons) or ("POLICY_PROPOSAL_NOT_ACTIONABLE",),
    )
