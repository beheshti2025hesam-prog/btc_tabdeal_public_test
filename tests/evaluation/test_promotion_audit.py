from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.operational_safety import OperationalSafetyEvidence
from core.evaluation.promotion_audit import PromotionAuditRecord
from core.evaluation.promotion_gate import PromotionEvidence
from core.evaluation.registry import EvidenceRegistry


def evidence(**overrides):
    values = dict(
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
    values.update(overrides)
    return PromotionEvidence(**values)


def ops(**overrides):
    values = dict(
        execution_disabled=True,
        venue_connection_disabled=True,
        capital_mutation_disabled=True,
        leverage_controlled=True,
        risk_veto_enforced=True,
        raw_data_immutable=True,
        audit_trail_available=True,
    )
    values.update(overrides)
    return OperationalSafetyEvidence(**values)


def setup():
    snapshot = EvidenceSnapshot.create(
        "HES Trade Agent",
        "Seyed Hesameddin Beheshti Shirazi",
        "abc123",
        {"data_quality_verified": True},
    )
    registry = EvidenceRegistry().append(snapshot)
    diagnostics = (("quality", "verified"), ("coverage", "complete"))
    return snapshot, registry, diagnostics


def test_audit_binds_snapshot_commit_registry_and_decision_inputs():
    snapshot, registry, diagnostics = setup()
    pe, safety = evidence(), ops()
    record = PromotionAuditRecord.create(
        snapshot, registry, pe, safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )
    assert record.eligible is True
    assert record.verify_binding(
        snapshot,
        current_source_commit="abc123",
        registry=registry,
        promotion_evidence=pe,
        operational_safety=safety,
        diagnostics=diagnostics,
    )


def test_changed_registry_fails_binding():
    snapshot, registry, diagnostics = setup()
    pe, safety = evidence(), ops()
    record = PromotionAuditRecord.create(
        snapshot, registry, pe, safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )
    extra = EvidenceSnapshot.create(
        "HES Trade Agent",
        "Seyed Hesameddin Beheshti Shirazi",
        "abc123",
        {"extra": True},
    )
    changed_registry = registry.append(extra)
    assert not record.verify_binding(
        snapshot,
        current_source_commit="abc123",
        registry=changed_registry,
        promotion_evidence=pe,
        operational_safety=safety,
        diagnostics=diagnostics,
    )


def test_changed_promotion_input_fails_binding():
    snapshot, registry, diagnostics = setup()
    pe, safety = evidence(), ops()
    record = PromotionAuditRecord.create(
        snapshot, registry, pe, safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )
    assert not record.verify_binding(
        snapshot,
        current_source_commit="abc123",
        registry=registry,
        promotion_evidence=evidence(paper_robustness_verified=False),
        operational_safety=safety,
        diagnostics=diagnostics,
    )


def test_changed_operational_safety_fails_binding():
    snapshot, registry, diagnostics = setup()
    pe, safety = evidence(), ops()
    record = PromotionAuditRecord.create(
        snapshot, registry, pe, safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )
    assert not record.verify_binding(
        snapshot,
        current_source_commit="abc123",
        registry=registry,
        promotion_evidence=pe,
        operational_safety=ops(risk_veto_enforced=False),
        diagnostics=diagnostics,
    )


def test_changed_diagnostics_fails_binding():
    snapshot, registry, diagnostics = setup()
    pe, safety = evidence(), ops()
    record = PromotionAuditRecord.create(
        snapshot, registry, pe, safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )
    assert not record.verify_binding(
        snapshot,
        current_source_commit="abc123",
        registry=registry,
        promotion_evidence=pe,
        operational_safety=safety,
        diagnostics=(("quality", "tampered"), ("coverage", "complete")),
    )


def test_replay_matches_exact_final_gate_result():
    snapshot, registry, diagnostics = setup()
    pe, safety = evidence(), ops()
    record = PromotionAuditRecord.create(
        snapshot, registry, pe, safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )
    assert record.replay_matches(
        snapshot,
        registry,
        pe,
        safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )


def test_replay_rejects_changed_gate_inputs():
    snapshot, registry, diagnostics = setup()
    pe, safety = evidence(), ops()
    record = PromotionAuditRecord.create(
        snapshot, registry, pe, safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )
    assert not record.replay_matches(
        snapshot,
        registry,
        evidence(paper_performance_verified=False),
        safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )


def test_audit_binding_covers_all_promotion_and_safety_fields():
    snapshot, registry, diagnostics = setup()
    pe, safety = evidence(), ops()
    record = PromotionAuditRecord.create(
        snapshot, registry, pe, safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )
    assert record.decision_input_digest
    assert record.replay_matches(
        snapshot, registry, pe, safety,
        current_source_commit="abc123",
        diagnostics=diagnostics,
    )
    for field in (
        "data_quality_verified",
        "historical_validation_verified",
        "oos_walk_forward_verified",
        "oos_stability_verified",
        "paper_validation_verified",
        "paper_performance_verified",
        "paper_robustness_verified",
        "risk_boundary_verified",
        "live_safety_verified",
    ):
        changed = evidence(**{field: False})
        assert not record.replay_matches(
            snapshot, registry, changed, safety,
            current_source_commit="abc123",
            diagnostics=diagnostics,
        )
    for field in (
        "execution_disabled",
        "venue_connection_disabled",
        "capital_mutation_disabled",
        "leverage_controlled",
        "risk_veto_enforced",
        "raw_data_immutable",
        "audit_trail_available",
    ):
        changed = ops(**{field: False})
        assert not record.replay_matches(
            snapshot, registry, pe, changed,
            current_source_commit="abc123",
            diagnostics=diagnostics,
        )
