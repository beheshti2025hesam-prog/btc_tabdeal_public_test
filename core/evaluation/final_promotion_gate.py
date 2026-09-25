"""Final promotion gate for HES Trade Agent.

This gate evaluates existing evidence only. It never executes trades, connects
to a venue, mutates capital, sets leverage, or enables live execution.
"""

from dataclasses import dataclass
from typing import Iterable

from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.operational_safety import OperationalSafetyEvidence
from core.evaluation.promotion_gate import PromotionEvidence, PromotionGate
from core.evaluation.registry import EvidenceRegistry, EvidenceRegistryValidator


@dataclass(frozen=True)
class FinalPromotionResult:
    eligible: bool
    missing: tuple[str, ...]


class FinalPromotionGate:
    """Final evidence-only gate before any future execution layer."""

    def evaluate(
        self,
        promotion_evidence: PromotionEvidence,
        snapshot: EvidenceSnapshot,
        registry: EvidenceRegistry,
        operational_safety: OperationalSafetyEvidence,
        *,
        current_source_commit: str,
    ) -> FinalPromotionResult:
        missing: list[str] = []

        if not PromotionGate().evaluate(promotion_evidence).eligible:
            missing.extend(PromotionGate().evaluate(promotion_evidence).missing)

        registry_result = EvidenceRegistryValidator(
            current_source_commit=current_source_commit,
            canonical_project_name="HES Trade Agent",
            canonical_owner="Seyed Hesameddin Beheshti Shirazi",
        ).validate(snapshot, registry)

        if not registry_result.valid:
            missing.append(registry_result.reason)

        if not operational_safety.verify():
            missing.append("operational_safety_unverified")

        return FinalPromotionResult(
            eligible=not missing,
            missing=tuple(dict.fromkeys(missing)),
        )
