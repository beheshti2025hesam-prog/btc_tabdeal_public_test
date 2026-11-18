"""Blackbox V1: fail-closed research brain readiness evaluator.

It reuses HES training artifacts and the canonical strategy-learning report.
It is deliberately not a signal generator and cannot mutate policy or execute.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from .blackbox_experience_memory_v1 import collect_canonical_experiences


@dataclass(frozen=True)
class Artifact:
    path: Path
    payload: dict[str, Any]
    sha256: str


def _load(path: Path) -> Artifact:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"BLACKBOX_ARTIFACT_NOT_OBJECT:{path.name}")
    return Artifact(path, payload, hashlib.sha256(raw).hexdigest())


def _safe_research_artifact(payload: dict[str, Any]) -> bool:
    safety = payload.get("safety")
    return isinstance(safety, dict) and all(
        safety.get(key) is False
        for key in ("execution_enabled", "orders_placed", "policy_mutation_enabled",
                    "production_approved", "risk_gate_bypass", "trading_signal_output")
    )


def assess_blackbox_readiness(
    *,
    data_root: str | Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return an auditable readiness report; never returns LONG/SHORT candidates."""
    root = Path(data_root)
    training = root / "data" / "training"
    forward = root / "data" / "forward"
    paths = {
        "regime_model": training / "hes_market_regime_model_v2.json",
        "regime_run": training / "hes_market_regime_training_run_v2.json",
        "movement_model": training / "hes_supervised_market_movement_model_v1.json",
        "movement_run": training / "hes_supervised_market_movement_run_v1.json",
        "strategy_learning": forward / "strategy_learning_v1_report.json",
    }
    artifacts = {name: _load(path) for name, path in paths.items()}
    reasons: list[str] = []

    regime_model = artifacts["regime_model"].payload
    regime_run = artifacts["regime_run"].payload
    movement_model = artifacts["movement_model"].payload
    movement_run = artifacts["movement_run"].payload
    learning = artifacts["strategy_learning"].payload

    for name in ("regime_run", "movement_run"):
        if not _safe_research_artifact(artifacts[name].payload):
            reasons.append(f"{name.upper()}_SAFETY_METADATA_INVALID")
    if regime_model.get("schema") != "hes_unsupervised_market_regime_model_v2":
        reasons.append("REGIME_MODEL_SCHEMA_UNSUPPORTED")
    if movement_model.get("schema") != "hes_supervised_market_movement_model_v1":
        reasons.append("MOVEMENT_MODEL_SCHEMA_UNSUPPORTED")

    if regime_run.get("model_sha256") != artifacts["regime_model"].sha256:
        reasons.append("REGIME_MODEL_HASH_MISMATCH")
    if movement_run.get("model_sha256") != artifacts["movement_model"].sha256:
        reasons.append("MOVEMENT_MODEL_HASH_MISMATCH")

    if regime_run.get("status") != "COMPLETED_RESEARCH_ONLY":
        reasons.append("REGIME_MODEL_NOT_RESEARCH_COMPLETE")
    if movement_run.get("status") != "RESEARCH_ONLY_EVALUATED_NOT_APPROVED":
        reasons.append("MOVEMENT_MODEL_NOT_EVALUATED_RESEARCH_ONLY")

    resolved = int(learning.get("resolved_outcomes", 0) or 0)
    eligible_candidates = int(learning.get("gate_approved_candidate_count", 0) or 0)
    unmatched = int(learning.get("unmatched_outcome_count", 0) or 0)
    ambiguous = int(learning.get("ambiguous_legacy_outcome_match_count", 0) or 0)
    if resolved < 100:
        reasons.append("INSUFFICIENT_GATE_APPROVED_MATURED_TRADE_OUTCOMES")
    if eligible_candidates == 0:
        reasons.append("NO_GATE_APPROVED_STRATEGY_CANDIDATES")
    if unmatched or ambiguous:
        reasons.append("OUTCOME_LINKAGE_NOT_CLEAN")

    wf = movement_run.get("walk_forward", {})
    lift = wf.get("accuracy_lift_over_mean_majority_baseline") if isinstance(wf, dict) else None
    if not isinstance(lift, (int, float)) or lift <= 0:
        reasons.append("MOVEMENT_MODEL_WALK_FORWARD_EDGE_NOT_ESTABLISHED")

    experience_events, experience_sources = collect_canonical_experiences(root)
    experience_memory = {
        "schema": "hes_blackbox_experience_memory_preview_v1",
        "events_indexed": len(experience_events),
        "training_eligible_events": sum(bool(item.get("training_eligible")) for item in experience_events),
        "four_state_counts": {state: sum(item.get("regime") == state for item in experience_events)
                              for state in ("BULLISH", "BEARISH", "RANGE", "NO_TRADE")},
        "experience_type_counts": {kind: sum(item.get("experience_type") == kind for item in experience_events)
                                   for kind in ("TRADE_OUTCOME", "NO_TRADE_COUNTERFACTUAL", "REJECTED_PROPOSAL", "MARKET_CONTEXT", "FAMILY_RESEARCH")},
        "source_counts": experience_sources,
        "append_only_persistence_enabled": False,
    }
    created = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "schema": "hes_blackbox_strategy_brain_readiness_v1",
        "generated_at": created,
        "brain_id": "HES-BLACKBOX-STRATEGY-BRAIN",
        "version": "0.1.0",
        "status": "RESEARCH_FOUNDATION_READY_BRAIN_TRAINING_BLOCKED",
        "decision": "NO_TRADE",
        "signal_candidates": [],
        "mode": "READ_ONLY_RESEARCH_ONLY",
        "reused_existing_components": [
            "Gate.io canonical 1m/15m/1h/4h market data",
            "existing unsupervised market-regime model V2",
            "existing supervised market-movement model V1 (diagnostic only)",
            "canonical strategy-learning loop and gate-approved outcome ledger",
            "Adaptive Hybrid, structure and Order Block evidence providers",
        ],
        "evidence": {
            name: {"path": str(item.path), "sha256": item.sha256}
            for name, item in artifacts.items()
        },
        "experiential_memory": experience_memory,
        "training_evidence": {
            "regime_model_samples": regime_run.get("feature_rows"),
            "movement_model_samples": movement_run.get("dataset", {}).get("samples"),
            "movement_walk_forward_accuracy_lift": lift,
            "gate_approved_candidates": eligible_candidates,
            "matured_gate_approved_resolved_outcomes": resolved,
            "unmatched_outcomes": unmatched,
            "ambiguous_outcomes": ambiguous,
        },
        "blocking_reasons": sorted(set(reasons)),
        "safety": {
            "execution_enabled": False,
            "orders_placed": False,
            "policy_mutation_enabled": False,
            "production_approved": False,
            "risk_gate_bypass": False,
            "trading_signal_output": False,
            "risk_gate_is_external_and_mandatory": True,
        },
    }
