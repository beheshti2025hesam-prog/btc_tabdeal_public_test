"""Immutable audit record for promotion evidence.

Validation-only contract. It records the canonical snapshot digest and the
promotion decision inputs without executing or enabling anything.
"""
from dataclasses import dataclass
from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.registry import EvidenceRegistry
from core.evaluation.promotion_gate import PromotionEvidence
from core.evaluation.operational_safety import OperationalSafetyEvidence


@dataclass(frozen=True)
class PromotionAuditRecord:
    snapshot_digest: str
    source_commit: str
    eligible: bool
    missing: tuple[str, ...]

    @classmethod
    def create(
        cls,
        snapshot: EvidenceSnapshot,
        registry: EvidenceRegistry,
        promotion_evidence: PromotionEvidence,
        operational_safety: OperationalSafetyEvidence,
        *,
        current_source_commit: str,
    ) -> "PromotionAuditRecord":
        from core.evaluation.final_promotion_gate import FinalPromotionGate

        result = FinalPromotionGate().evaluate(
            promotion_evidence,
            snapshot,
            registry,
            operational_safety,
            current_source_commit=current_source_commit,
        )
        return cls(
            snapshot_digest=snapshot.digest,
            source_commit=current_source_commit,
            eligible=result.eligible,
            missing=result.missing,
        )

    def verify_binding(self, snapshot: EvidenceSnapshot, *, current_source_commit: str) -> bool:
        return (
            snapshot.verify()
            and snapshot.digest == self.snapshot_digest
            and self.source_commit == current_source_commit
        )
