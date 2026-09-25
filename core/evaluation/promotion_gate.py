"""Explicit, execution-free promotion evidence gate.

This module does not score strategies or enable execution. It only verifies that
required evidence artifacts have been explicitly supplied and are structurally
complete. Policy thresholds remain external to this contract.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PromotionEvidence:
    data_quality_verified: bool
    historical_validation_verified: bool
    oos_walk_forward_verified: bool
    oos_stability_verified: bool
    paper_validation_verified: bool
    paper_performance_verified: bool
    paper_robustness_verified: bool
    risk_boundary_verified: bool
    live_safety_verified: bool = False


@dataclass(frozen=True)
class PromotionGateResult:
    eligible: bool
    missing: tuple[str, ...]


class PromotionGate:
    """Evaluate evidence completeness without ranking or executing anything."""

    def evaluate(self, evidence: PromotionEvidence) -> PromotionGateResult:
        required = {
            "data_quality_verified": evidence.data_quality_verified,
            "historical_validation_verified": evidence.historical_validation_verified,
            "oos_walk_forward_verified": evidence.oos_walk_forward_verified,
            "oos_stability_verified": evidence.oos_stability_verified,
            "paper_validation_verified": evidence.paper_validation_verified,
            "paper_performance_verified": evidence.paper_performance_verified,
            "paper_robustness_verified": evidence.paper_robustness_verified,
            "risk_boundary_verified": evidence.risk_boundary_verified,
            "live_safety_verified": evidence.live_safety_verified,
        }
        missing = tuple(name for name, present in required.items() if not present)
        return PromotionGateResult(eligible=not missing, missing=missing)
