from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.final_promotion_gate import FinalPromotionGate
from core.evaluation.operational_safety import OperationalSafetyEvidence
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


def canonical(source="abc123"):
    snapshot = EvidenceSnapshot.create(
        "HES Trade Agent",
        "Seyed Hesameddin Beheshti Shirazi",
        source,
        {"data_quality_verified": True},
    )
    return snapshot, EvidenceRegistry().append(snapshot)


def test_gate_is_eligible_only_when_every_boundary_is_valid():
    snapshot, registry = canonical()
    result = FinalPromotionGate().evaluate(
        evidence(), snapshot, registry, ops(), current_source_commit="abc123"
    )
    assert result.eligible is True
    assert result.missing == ()


def test_gate_fails_closed_for_missing_promotion_evidence():
    snapshot, registry = canonical()
    result = FinalPromotionGate().evaluate(
        evidence(paper_robustness_verified=False),
        snapshot, registry, ops(), current_source_commit="abc123"
    )
    assert result.eligible is False
    assert "paper_robustness_verified" in result.missing


def test_gate_fails_closed_for_unverified_operational_safety():
    snapshot, registry = canonical()
    result = FinalPromotionGate().evaluate(
        evidence(), snapshot, registry, ops(risk_veto_enforced=False),
        current_source_commit="abc123"
    )
    assert result.eligible is False
    assert "operational_safety_unverified" in result.missing


def test_gate_fails_closed_for_unregistered_snapshot():
    snapshot, _ = canonical()
    result = FinalPromotionGate().evaluate(
        evidence(), snapshot, EvidenceRegistry(), ops(), current_source_commit="abc123"
    )
    assert result.eligible is False
    assert "snapshot_not_registered" in result.missing


def test_gate_fails_closed_for_stale_source_commit():
    snapshot, registry = canonical("old")
    result = FinalPromotionGate().evaluate(
        evidence(), snapshot, registry, ops(), current_source_commit="new"
    )
    assert result.eligible is False
    assert "stale_source_commit" in result.missing
