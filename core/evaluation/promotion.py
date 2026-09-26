"""Execution-free promotion eligibility contract.

This module evaluates immutable evidence against explicit required gates.
It does not rank candidates, optimize parameters, promote deployments,
execute orders, size positions, set leverage, or connect to a venue.
"""

from dataclasses import dataclass

from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.registry import EvidenceRegistry
from core.evaluation.registry import EvidenceRegistryValidator
from core.evaluation.schema import EvidenceGateSchema


@dataclass(frozen=True)
class PromotionGateResult:
    """Immutable result of a promotion-eligibility evaluation."""

    eligible: bool
    reasons: tuple[str, ...]


class PromotionGate:
    """Evaluate whether evidence satisfies an explicit promotion contract."""

    def __init__(self, validator: EvidenceRegistryValidator | None = None) -> None:
        self._validator = validator or EvidenceRegistryValidator()

    def evaluate_registry(
        self,
        registry: EvidenceRegistry,
        current_source_commit: str,
        required_evidence: tuple[str, ...] | EvidenceGateSchema,
    ) -> PromotionGateResult:
        """Evaluate the latest registered snapshot without mutating the registry."""
        snapshot = registry.latest()
        if snapshot is None:
            return PromotionGateResult(False, ("empty_evidence_registry",))
        return self.evaluate(snapshot, current_source_commit, required_evidence)

    def evaluate(
        self,
        snapshot: EvidenceSnapshot,
        current_source_commit: str,
        required_evidence: tuple[str, ...] | EvidenceGateSchema,
    ) -> PromotionGateResult:
        reasons: list[str] = []

        if not isinstance(current_source_commit, str) or not current_source_commit.strip():
            reasons.append("invalid_current_source_commit")

        if isinstance(required_evidence, EvidenceGateSchema):
            required_names = required_evidence.as_required_evidence()
        else:
            required_names = required_evidence

        if not required_names:
            return PromotionGateResult(
                False,
                tuple(reasons) + ("no_required_gates",),
            )

        normalized: list[str] = []
        for name in required_names:
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
