"""Execution-free promotion eligibility contract.

This module evaluates immutable evidence against explicit required gates.
It does not rank candidates, optimize parameters, promote deployments,
execute orders, size positions, set leverage, or connect to a venue.
"""

from dataclasses import dataclass

from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.registry import EvidenceRegistryValidator


@dataclass(frozen=True)
class PromotionGateResult:
    """Immutable result of a promotion-eligibility evaluation."""

    eligible: bool
    reasons: tuple[str, ...]


class PromotionGate:
    """Evaluate whether evidence satisfies an explicit promotion contract."""

    def __init__(self, validator: EvidenceRegistryValidator | None = None) -> None:
        self._validator = validator or EvidenceRegistryValidator()

    def evaluate(
        self,
        snapshot: EvidenceSnapshot,
        current_source_commit: str,
        required_evidence: tuple[str, ...],
    ) -> PromotionGateResult:
        reasons: list[str] = []

        if not isinstance(current_source_commit, str) or not current_source_commit.strip():
            reasons.append("invalid_current_source_commit")

        if not required_evidence:
            return PromotionGateResult(
                False,
                tuple(reasons) + ("no_required_gates",),
            )

        normalized: list[str] = []
        for name in required_evidence:
            if not isinstance(name, str) or not name.strip():
                reasons.append("invalid_required_gate_name")
                continue
            if name not in normalized:
                normalized.append(name)

        freshness = self._validator.validate(snapshot, current_source_commit)
        reasons.extend(freshness.reasons)

        evidence = dict(snapshot.evidence)
        for name in normalized:
            if name not in evidence:
                reasons.append(f"missing_evidence:{name}")
            elif evidence.get(name) is not True:
                reasons.append(f"failed_evidence:{name}")

        return PromotionGateResult(eligible=not reasons, reasons=tuple(reasons))
