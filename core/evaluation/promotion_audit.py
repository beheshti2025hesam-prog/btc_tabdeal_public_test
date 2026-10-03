"""Immutable, tamper-evident audit record for promotion evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from core.evaluation.diagnostics import diagnostics_digest
from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.operational_safety import OperationalSafetyEvidence
from core.evaluation.promotion_gate import PromotionEvidence
from core.evaluation.registry import EvidenceRegistry


def _registry_digest(registry: EvidenceRegistry) -> str:
    payload = json.dumps(
        tuple(snapshot.digest for snapshot in registry.snapshots),
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _decision_input_digest(
    promotion_evidence: PromotionEvidence,
    operational_safety: OperationalSafetyEvidence,
    diagnostics: tuple[tuple[str, str], ...],
) -> str:
    payload = {
        "promotion_evidence": {
            name: getattr(promotion_evidence, name)
            for name in (
                "data_quality_verified",
                "historical_validation_verified",
                "oos_walk_forward_verified",
                "oos_stability_verified",
                "paper_validation_verified",
                "paper_performance_verified",
                "paper_robustness_verified",
                "risk_boundary_verified",
                "live_safety_verified",
            )
        },
        "operational_safety": {
            name: getattr(operational_safety, name)
            for name in (
                "execution_disabled",
                "venue_connection_disabled",
                "capital_mutation_disabled",
                "leverage_controlled",
                "risk_veto_enforced",
                "raw_data_immutable",
                "audit_trail_available",
            )
        },
        "diagnostics_digest": diagnostics_digest(diagnostics),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PromotionAuditRecord:
    snapshot_digest: str
    registry_digest: str
    source_commit: str
    decision_input_digest: str
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
        diagnostics: tuple[tuple[str, str], ...] = (),
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
            registry_digest=_registry_digest(registry),
            source_commit=current_source_commit,
            decision_input_digest=_decision_input_digest(
                promotion_evidence, operational_safety, diagnostics
            ),
            eligible=result.eligible,
            missing=result.missing,
        )

    def verify_binding(
        self,
        snapshot: EvidenceSnapshot,
        *,
        current_source_commit: str,
        registry: EvidenceRegistry | None = None,
        promotion_evidence: PromotionEvidence | None = None,
        operational_safety: OperationalSafetyEvidence | None = None,
        diagnostics: tuple[tuple[str, str], ...] | None = None,
    ) -> bool:
        if not (
            snapshot.verify()
            and snapshot.digest == self.snapshot_digest
            and self.source_commit == current_source_commit
        ):
            return False
        if registry is not None and _registry_digest(registry) != self.registry_digest:
            return False
        if promotion_evidence is None or operational_safety is None or diagnostics is None:
            return True
        return self.decision_input_digest == _decision_input_digest(
            promotion_evidence, operational_safety, diagnostics
        )

    def replay_matches(
        self,
        snapshot: EvidenceSnapshot,
        registry: EvidenceRegistry,
        promotion_evidence: PromotionEvidence,
        operational_safety: OperationalSafetyEvidence,
        *,
        current_source_commit: str,
        diagnostics: tuple[tuple[str, str], ...] = (),
    ) -> bool:
        """Re-evaluate the gate and require exact audit/result equivalence."""
        if not self.verify_binding(
            snapshot,
            current_source_commit=current_source_commit,
            registry=registry,
            promotion_evidence=promotion_evidence,
            operational_safety=operational_safety,
            diagnostics=diagnostics,
        ):
            return False

        from core.evaluation.final_promotion_gate import FinalPromotionGate

        result = FinalPromotionGate().evaluate(
            promotion_evidence,
            snapshot,
            registry,
            operational_safety,
            current_source_commit=current_source_commit,
        )
        return result.eligible == self.eligible and result.missing == self.missing
