import pytest
from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.operational_safety import OperationalSafetyEvidence
from core.evaluation.promotion_audit import PromotionAuditRecord
from core.evaluation.promotion_gate import PromotionEvidence
from core.evaluation.registry import EvidenceRegistry


def all_promotion_evidence():
    return PromotionEvidence(
        data_quality_verified=True,
        historical_validation_verified=True,
        oos_walk_forward_verified=True,
        oos_stability_verified=True,
        paper_validation_verified=True,
        paper_performance_verified=True,
        paper_robustness_verified=True,
        risk_boundary_verified=True,
        live_safety_verified=True,
    )


def safe_ops():
    return OperationalSafetyEvidence(True, True, True, True, True, True, True)


def test_audit_record_binds_to_snapshot_and_commit():
    snapshot = EvidenceSnapshot.create(
        "HES Trade Agent",
        "Seyed Hesameddin Beheshti Shirazi",
        "abc123",
        {"data_quality_verified": True},
    )
    registry = EvidenceRegistry().append(snapshot)
    record = PromotionAuditRecord.create(
        snapshot, registry, all_promotion_evidence(), safe_ops(),
        current_source_commit="abc123",
    )
    assert record.eligible is True
    assert record.verify_binding(snapshot, current_source_commit="abc123")


def test_tampered_snapshot_fails_audit_binding():
    snapshot = EvidenceSnapshot.create(
        "HES Trade Agent",
        "Seyed Hesameddin Beheshti Shirazi",
        "abc123",
        {"data_quality_verified": True},
    )
    registry = EvidenceRegistry().append(snapshot)
    record = PromotionAuditRecord.create(
        snapshot, registry, all_promotion_evidence(), safe_ops(),
        current_source_commit="abc123",
    )
    tampered = EvidenceSnapshot.create(
        "HES Trade Agent",
        "Seyed Hesameddin Beheshti Shirazi",
        "abc123",
        {"data_quality_verified": False},
    )
    assert not record.verify_binding(tampered, current_source_commit="abc123")


def test_stale_commit_fails_audit_binding():
    snapshot = EvidenceSnapshot.create(
        "HES Trade Agent",
        "Seyed Hesameddin Beheshti Shirazi",
        "abc123",
        {"data_quality_verified": True},
    )
    registry = EvidenceRegistry().append(snapshot)
    record = PromotionAuditRecord.create(
        snapshot, registry, all_promotion_evidence(), safe_ops(),
        current_source_commit="abc123",
    )
    assert not record.verify_binding(snapshot, current_source_commit="def456")
