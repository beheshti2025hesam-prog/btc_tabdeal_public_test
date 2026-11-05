"""Versioned, provenance-bound envelope for strategy-family research candidates.

This is an evidence transport contract only. It does not turn a candidate into
an approved setup, confirmation, risk approval, or executable instruction.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping

from .strategy_family_router_v1 import (
    CANONICAL_SOURCE,
    CANONICAL_SYMBOL,
    RANGE_MEAN_REVERSION_RESEARCH_V1,
    ROUTER_VERSION,
    SETUP_TIMEFRAME,
    TREND_BREAKOUT_V2,
    route_strategy_family,
)

SCHEMA = "hes_strategy_family_candidate_context_v1"
CONTEXT_VERSION = "hes-strategy-family-context-v1.0.0"
_ALLOWED_DIRECTIONS = {"LONG", "SHORT"}


def _canonical_hash(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _payload_binding_error(*, candidate: Mapping[str, Any], gate_evidence: Mapping[str, Any],
                           source: str, symbol: str, timeframe: str, regime: str,
                           direction: str, family_id: str, family_version: str,
                           activation_state: str, router_version: str,
                           observed_at: datetime) -> str | None:
    """Reject internally valid hashes whose nested evidence describes another setup."""
    for key, expected in (("symbol", symbol), ("timeframe", timeframe), ("regime", regime)):
        if key in candidate and candidate.get(key) != expected:
            return "FAMILY_CONTEXT_CANDIDATE_" + key.upper() + "_MISMATCH"
    candidate_direction = candidate.get("direction")
    state_direction = {"CANDIDATE_LONG": "LONG", "CANDIDATE_SHORT": "SHORT"}.get(candidate.get("state"))
    if candidate_direction is not None and candidate_direction != direction:
        return "FAMILY_CONTEXT_CANDIDATE_DIRECTION_MISMATCH"
    if state_direction is not None and state_direction != direction:
        return "FAMILY_CONTEXT_CANDIDATE_DIRECTION_MISMATCH"
    if "observed_at" in candidate:
        try:
            candidate_time = datetime.fromisoformat(str(candidate["observed_at"]).replace("Z", "+00:00"))
            if candidate_time.tzinfo is None or candidate_time.utcoffset() is None:
                raise ValueError
            if candidate_time.astimezone(timezone.utc) != observed_at.astimezone(timezone.utc):
                return "FAMILY_CONTEXT_CANDIDATE_TIME_MISMATCH"
        except (TypeError, ValueError):
            return "FAMILY_CONTEXT_CANDIDATE_TIME_INVALID"

    structure = gate_evidence.get("structure")
    if isinstance(structure, Mapping) and structure.get("regime") is not None and structure.get("regime") != regime:
        return "FAMILY_CONTEXT_STRUCTURE_REGIME_MISMATCH"
    route = gate_evidence.get("strategy_family_route")
    if route is not None:
        if not isinstance(route, Mapping):
            return "FAMILY_CONTEXT_ROUTE_EVIDENCE_INVALID"
        expected_route = {
            "router_version": router_version, "family_id": family_id,
            "family_version": family_version, "activation_state": activation_state,
            "regime": regime, "symbol": symbol, "timeframe": timeframe,
        }
        if any(route.get(key) != value for key, value in expected_route.items()):
            return "FAMILY_CONTEXT_ROUTE_EVIDENCE_MISMATCH"
        if route.get("candidate_generation_authorized") is not False or route.get("execution_enabled") is not False or route.get("orders_placed") is not False:
            return "FAMILY_CONTEXT_ROUTE_AUTHORITY_BOUNDARY_VIOLATION"
    return None


def build_strategy_family_context(
    *,
    source: str,
    symbol: str,
    timeframe: str,
    regime: str,
    direction: str,
    observed_at: datetime,
    candidate: Mapping[str, Any],
    gate_evidence: Mapping[str, Any],
) -> dict:
    """Build an immutable-by-digest evidence envelope; never authorize trading."""
    if source != CANONICAL_SOURCE or symbol != CANONICAL_SYMBOL or timeframe != SETUP_TIMEFRAME:
        raise ValueError("FAMILY_CONTEXT_SCOPE_INVALID")
    if direction not in _ALLOWED_DIRECTIONS:
        raise ValueError("FAMILY_CONTEXT_DIRECTION_INVALID")
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("FAMILY_CONTEXT_TIME_NOT_TIMEZONE_AWARE")
    if not isinstance(candidate, Mapping) or not candidate:
        raise ValueError("FAMILY_CONTEXT_CANDIDATE_MISSING")
    if not isinstance(gate_evidence, Mapping) or not gate_evidence:
        raise ValueError("FAMILY_CONTEXT_GATE_EVIDENCE_MISSING")

    route = route_strategy_family(source=source, symbol=symbol, timeframe=timeframe, regime=regime)
    if route.family_id is None:
        raise ValueError("FAMILY_CONTEXT_NO_ROUTABLE_FAMILY")
    profile = TREND_BREAKOUT_V2 if route.family_id == TREND_BREAKOUT_V2.family_id else RANGE_MEAN_REVERSION_RESEARCH_V1
    if profile.activation_state != route.activation_state:
        raise ValueError("FAMILY_CONTEXT_PROFILE_VERSION_MISMATCH")
    if (regime == "UPTREND" and direction != "LONG") or (regime == "DOWNTREND" and direction != "SHORT"):
        raise ValueError("FAMILY_CONTEXT_DIRECTION_REGIME_MISMATCH")

    candidate_payload = dict(candidate)
    evidence_payload = dict(gate_evidence)
    binding_error = _payload_binding_error(
        candidate=candidate_payload, gate_evidence=evidence_payload,
        source=source, symbol=symbol, timeframe=timeframe, regime=regime,
        direction=direction, family_id=profile.family_id, family_version=profile.version,
        activation_state=profile.activation_state, router_version=ROUTER_VERSION,
        observed_at=observed_at,
    )
    if binding_error:
        raise ValueError(binding_error)
    # JSON canonicalization rejects NaN, non-serializable objects and unstable payloads.
    candidate_digest = _canonical_hash(candidate_payload)
    gate_digest = _canonical_hash(evidence_payload)

    base = {
        "schema": SCHEMA,
        "context_version": CONTEXT_VERSION,
        "router_version": ROUTER_VERSION,
        "family_id": profile.family_id,
        "family_version": profile.version,
        "family_activation_state": profile.activation_state,
        "source": source,
        "symbol": symbol,
        "setup_timeframe": timeframe,
        "precision_timeframe": profile.precision_timeframe,
        "regime": regime,
        "direction": direction,
        "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
        "candidate_sha256": candidate_digest,
        "gate_evidence_sha256": gate_digest,
        "candidate": candidate_payload,
        "gate_evidence": evidence_payload,
        "candidate_generation_authorized": False,
        "confirmation_approved": False,
        "risk_approved": False,
        "execution_enabled": False,
        "orders_placed": False,
    }
    return {**base, "context_sha256": _canonical_hash(base)}


def verify_strategy_family_context(
    context: Any,
    *,
    now: datetime,
    max_age_seconds: int = 900,
) -> tuple[bool, str | None]:
    if not isinstance(context, dict):
        return False, "FAMILY_CONTEXT_MISSING"
    if context.get("schema") != SCHEMA or context.get("context_version") != CONTEXT_VERSION:
        return False, "FAMILY_CONTEXT_SCHEMA_INVALID"
    digest = context.get("context_sha256")
    base = {k: v for k, v in context.items() if k != "context_sha256"}
    try:
        if _canonical_hash(base) != digest:
            return False, "FAMILY_CONTEXT_DIGEST_MISMATCH"
        if _canonical_hash(context["candidate"]) != context.get("candidate_sha256"):
            return False, "FAMILY_CONTEXT_CANDIDATE_DIGEST_MISMATCH"
        if _canonical_hash(context["gate_evidence"]) != context.get("gate_evidence_sha256"):
            return False, "FAMILY_CONTEXT_GATE_DIGEST_MISMATCH"
    except (KeyError, TypeError, ValueError):
        return False, "FAMILY_CONTEXT_PAYLOAD_INVALID"

    if (context.get("source"), context.get("symbol"), context.get("setup_timeframe")) != (
        CANONICAL_SOURCE, CANONICAL_SYMBOL, SETUP_TIMEFRAME
    ):
        return False, "FAMILY_CONTEXT_SCOPE_INVALID"
    route = route_strategy_family(
        source=context["source"], symbol=context["symbol"],
        timeframe=context["setup_timeframe"], regime=context.get("regime"),
    )
    if route.family_id != context.get("family_id") or route.family_version != context.get("family_version"):
        return False, "FAMILY_CONTEXT_ROUTE_MISMATCH"
    if route.activation_state != context.get("family_activation_state"):
        return False, "FAMILY_CONTEXT_ACTIVATION_STATE_MISMATCH"
    profile = TREND_BREAKOUT_V2 if route.family_id == TREND_BREAKOUT_V2.family_id else RANGE_MEAN_REVERSION_RESEARCH_V1
    if context.get("precision_timeframe") != profile.precision_timeframe:
        return False, "FAMILY_CONTEXT_PRECISION_TIMEFRAME_MISMATCH"
    if context.get("direction") not in _ALLOWED_DIRECTIONS:
        return False, "FAMILY_CONTEXT_DIRECTION_INVALID"
    if ((context.get("regime") == "UPTREND" and context.get("direction") != "LONG")
            or (context.get("regime") == "DOWNTREND" and context.get("direction") != "SHORT")):
        return False, "FAMILY_CONTEXT_DIRECTION_REGIME_MISMATCH"
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
        return False, "FAMILY_CONTEXT_MAX_AGE_INVALID"

    # These fields are invariants, not caller-controlled permissions.
    safety_false = (
        "candidate_generation_authorized", "confirmation_approved",
        "risk_approved", "execution_enabled", "orders_placed",
    )
    if any(context.get(key) is not False for key in safety_false):
        return False, "FAMILY_CONTEXT_AUTHORITY_BOUNDARY_VIOLATION"

    try:
        observed_for_binding = datetime.fromisoformat(str(context["observed_at"]).replace("Z", "+00:00"))
        binding_error = _payload_binding_error(
            candidate=context["candidate"], gate_evidence=context["gate_evidence"],
            source=context["source"], symbol=context["symbol"],
            timeframe=context["setup_timeframe"], regime=context["regime"],
            direction=context["direction"], family_id=profile.family_id,
            family_version=profile.version, activation_state=profile.activation_state,
            router_version=ROUTER_VERSION, observed_at=observed_for_binding,
        )
        if binding_error:
            return False, binding_error
    except (KeyError, TypeError, ValueError):
        return False, "FAMILY_CONTEXT_PAYLOAD_BINDING_INVALID"

    try:
        observed = datetime.fromisoformat(context["observed_at"])
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError
        age = (now.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
        if not math.isfinite(age) or age < 0 or age > max_age_seconds:
            return False, "FAMILY_CONTEXT_EXPIRED_OR_FUTURE"
    except (KeyError, TypeError, ValueError):
        return False, "FAMILY_CONTEXT_TIME_INVALID"
    return True, None
