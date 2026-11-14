"""Same-snapshot consensus adapter over existing Mother specialist outputs.

This module only translates already-computed stage evidence into the existing
AgentDisagreementResolverV1 contract. It does not fetch data or recompute signals.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Mapping

from forward.agent_disagreement_resolver_v1 import AgentAssessmentV1, AgentDisagreementResolverV1


_REQUIRED = (
    ("data_quality", "data_quality"),
    ("market_structure", "market_structure"),
    ("signal", "strategy"),
    ("confirmation", "confirmation"),
    ("risk", "risk"),
)


def _canonical_hash(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    except (TypeError, ValueError):
        return ""
    return sha256(raw).hexdigest()


def _stage_material(stage: Any) -> dict[str, Any]:
    return {
        "agent": getattr(stage, "agent", None),
        "agent_version": getattr(stage, "agent_version", None),
        "state": getattr(stage, "state", None),
        "reason_codes": getattr(stage, "reason_codes", None),
        "evidence_refs": getattr(stage, "evidence_refs", None),
        "payload": getattr(stage, "payload", None),
    }


def _assessment_state_direction(source_name: str, stage: Any) -> tuple[str, str]:
    state = getattr(stage, "state", None)
    payload = getattr(stage, "payload", None)
    payload = payload if isinstance(payload, Mapping) else {}

    if source_name == "data_quality":
        return ("PASS", "NEUTRAL") if state == "PASS" else ("UNKNOWN", "NEUTRAL")

    if source_name == "market_structure":
        regime = payload.get("regime")
        direction = {
            "UPTREND": "LONG",
            "DOWNTREND": "SHORT",
            "RANGE": "NEUTRAL",
        }.get(regime, "UNKNOWN")
        return ("PASS", direction) if state == "PASS" and direction != "UNKNOWN" else ("UNKNOWN", "UNKNOWN")

    if source_name == "signal":
        decision = payload.get("decision")
        direction = decision if decision in ("LONG", "SHORT") else ("NEUTRAL" if decision == "NO_TRADE" else "UNKNOWN")
        return ("PASS", direction) if state == "PASS" and direction != "UNKNOWN" else ("UNKNOWN", "UNKNOWN")

    if source_name == "confirmation":
        upstream = payload.get("upstream_state")
        if state == "CONFIRMED" and upstream in ("CONFIRMED_LONG", "CONFIRMED_SHORT"):
            return "PASS", upstream.removeprefix("CONFIRMED_")
        if state == "UNCONFIRMED":
            return "FAIL", "NEUTRAL"
        return "UNKNOWN", "UNKNOWN"

    if source_name == "risk":
        if state == "APPROVED":
            return "PASS", "NEUTRAL"
        if state == "REJECTED":
            return "FAIL", "NEUTRAL"
        return "UNKNOWN", "UNKNOWN"

    return "UNKNOWN", "UNKNOWN"


def resolve_mother_consensus_v1(*, context: Mapping[str, Any], stage_results: Mapping[str, Any]) -> dict[str, Any]:
    scope = context.get("scope") if isinstance(context, Mapping) else {}
    scope = scope if isinstance(scope, Mapping) else {}
    observed_raw = context.get("observed_at") if isinstance(context, Mapping) else None
    try:
        observed_at = datetime.fromisoformat(observed_raw.replace("Z", "+00:00")) if isinstance(observed_raw, str) else None
    except ValueError:
        observed_at = None

    assessments = []
    for source_name, agent_id in _REQUIRED:
        stage = stage_results.get(source_name) if isinstance(stage_results, Mapping) else None
        if stage is None:
            continue
        state, direction = _assessment_state_direction(source_name, stage)
        material = _stage_material(stage)
        evidence_sha = _canonical_hash(material)
        reason_codes = getattr(stage, "reason_codes", ())
        assessments.append(AgentAssessmentV1(
            agent_id=agent_id,
            agent_version=getattr(stage, "agent_version", ""),
            state=state,
            direction=direction,
            venue=scope.get("venue", ""),
            product=scope.get("product", ""),
            symbol=scope.get("symbol", ""),
            timeframe=scope.get("timeframe", ""),
            as_of=observed_at,
            snapshot_sha256=context.get("snapshot_sha256", "") if isinstance(context, Mapping) else "",
            evidence_sha256=evidence_sha,
            reason_codes=reason_codes,
        ))

    return AgentDisagreementResolverV1().resolve(
        assessments=assessments,
        observed_at=observed_at,
    ).as_dict()
