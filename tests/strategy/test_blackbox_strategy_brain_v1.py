import hashlib
import json
from pathlib import Path

from forward.blackbox_strategy_brain_v1 import assess_blackbox_readiness


def write_json(path: Path, value: dict) -> str:
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def build_fixture(root: Path, *, resolved=0, candidates=0, lift=-0.01):
    training = root / "data" / "training"
    forward = root / "data" / "forward"
    training.mkdir(parents=True)
    forward.mkdir(parents=True)
    safe = {k: False for k in (
        "execution_enabled", "orders_placed", "policy_mutation_enabled",
        "production_approved", "risk_gate_bypass", "trading_signal_output",
    )}
    regime_model = {"schema": "hes_unsupervised_market_regime_model_v2"}
    movement_model = {"schema": "hes_supervised_market_movement_model_v1"}
    regime_hash = write_json(training / "hes_market_regime_model_v2.json", regime_model)
    movement_hash = write_json(training / "hes_supervised_market_movement_model_v1.json", movement_model)
    write_json(training / "hes_market_regime_training_run_v2.json", {
        "status": "COMPLETED_RESEARCH_ONLY", "safety": safe,
        "model_sha256": regime_hash, "feature_rows": 1000,
    })
    write_json(training / "hes_supervised_market_movement_run_v1.json", {
        "status": "RESEARCH_ONLY_EVALUATED_NOT_APPROVED", "safety": safe,
        "model_sha256": movement_hash, "dataset": {"samples": 900},
        "walk_forward": {"accuracy_lift_over_mean_majority_baseline": lift},
    })
    write_json(forward / "strategy_learning_v1_report.json", {
        "resolved_outcomes": resolved, "gate_approved_candidate_count": candidates,
        "unmatched_outcome_count": 0, "ambiguous_legacy_outcome_match_count": 0,
    })


def test_blackbox_fails_closed_without_matured_trade_labels(tmp_path):
    build_fixture(tmp_path)
    report = assess_blackbox_readiness(data_root=tmp_path, generated_at="2026-11-18T00:00:00+00:00")
    assert report["status"] == "RESEARCH_FOUNDATION_READY_BRAIN_TRAINING_BLOCKED"
    assert report["decision"] == "NO_TRADE"
    assert report["signal_candidates"] == []
    assert report["experiential_memory"]["events_indexed"] == 0
    assert report["experiential_memory"]["training_eligible_events"] == 0
    assert report["experiential_memory"]["append_only_persistence_enabled"] is False
    assert "INSUFFICIENT_GATE_APPROVED_MATURED_TRADE_OUTCOMES" in report["blocking_reasons"]
    assert report["safety"]["execution_enabled"] is False


def test_blackbox_still_blocks_if_market_movement_model_has_no_walk_forward_edge(tmp_path):
    build_fixture(tmp_path, resolved=150, candidates=20, lift=0.0)
    report = assess_blackbox_readiness(data_root=tmp_path)
    assert "MOVEMENT_MODEL_WALK_FORWARD_EDGE_NOT_ESTABLISHED" in report["blocking_reasons"]
    assert report["decision"] == "NO_TRADE"


def test_blackbox_artifact_hash_mismatch_is_blocking(tmp_path):
    build_fixture(tmp_path)
    path = tmp_path / "data" / "training" / "hes_market_regime_model_v2.json"
    path.write_text('{"schema":"tampered"}')
    report = assess_blackbox_readiness(data_root=tmp_path)
    assert "REGIME_MODEL_HASH_MISMATCH" in report["blocking_reasons"]


def test_blackbox_can_only_become_ready_after_all_research_gates(tmp_path):
    build_fixture(tmp_path, resolved=150, candidates=20, lift=0.02)
    report = assess_blackbox_readiness(data_root=tmp_path)
    assert report["blocking_reasons"] == []
    assert report["decision"] == "NO_TRADE"
    assert report["signal_candidates"] == []
    assert report["safety"]["production_approved"] is False
