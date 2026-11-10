"""Research-only family dispatch; eligibility is never trade authorization.

Consumes validated, closed 15m Gate.io BTC_USDT context and evidence-bound
features. It does not create candidates, confirm trades, approve risk or enable
execution. The existing production family router is intentionally untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA = "hes_strategy_family_research_dispatch_v1"
VERSION = "hes-strategy-family-research-dispatch-v1.0.0"
SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"
SETUP_TIMEFRAME = "15m"
PRECISION_TIMEFRAME = "1m"
MAX_AGE_SECONDS = 900

FAMILIES = {
    "trend_continuation": {
        "version": "hes-trend-continuation-research-v1.0.0",
        "regimes": ("UPTREND", "DOWNTREND"),
        "features": ("trend_persistent", "pullback_at_value", "continuation_structure", "directional_flow"),
    },
    "breakout_retest": {
        "version": "hes-breakout-retest-research-v1.0.0",
        "regimes": ("UPTREND", "DOWNTREND", "RANGE"),
        "features": ("breakout_closed", "acceptance_outside_boundary", "retest_confirmed", "directional_flow"),
    },
    "range_reversion": {
        "version": "hes-range-reversion-research-v1.0.0",
        "regimes": ("RANGE",),
        "features": ("range_persistent", "at_range_boundary", "liquidity_sweep_reclaim", "reversal_structure", "directional_flow"),
    },
    "volatility_expansion": {
        "version": "hes-volatility-expansion-research-v1.0.0",
        "regimes": ("UPTREND", "DOWNTREND", "RANGE"),
        "features": ("compression_preceded", "volatility_expansion_confirmed", "directional_displacement", "structure_confirmation", "directional_flow"),
    },
}


def _parse_aware(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _blocked(reason: str, regime: str = "UNKNOWN") -> dict[str, Any]:
    return {
        "schema": SCHEMA, "version": VERSION, "status": "BLOCKED",
        "reason_codes": [reason], "regime": regime,
        "research_eligible_families": [],
        "candidate_generation_authorized": False,
        "confirmation_approved": False, "risk_approved": False,
        "family_live_activation": False, "execution_enabled": False,
        "orders_placed": False,
    }


def dispatch_research_families(
    *, source: str, symbol: str, timeframe: str, regime: str,
    closed_candle: bool, observed_at: Any, now: Any,
    feature_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Return research evaluator eligibility only; fail closed on any bad input."""
    if source != SOURCE:
        return _blocked("NON_CANONICAL_SOURCE", regime if isinstance(regime, str) else "UNKNOWN")
    if symbol != SYMBOL:
        return _blocked("SYMBOL_OUT_OF_SCOPE", regime if isinstance(regime, str) else "UNKNOWN")
    if timeframe != SETUP_TIMEFRAME:
        reason = "PRECISION_1M_CANNOT_ORIGINATE_SETUP" if timeframe == PRECISION_TIMEFRAME else "SETUP_TIMEFRAME_INVALID"
        return _blocked(reason, regime if isinstance(regime, str) else "UNKNOWN")
    if closed_candle is not True:
        return _blocked("CLOSED_15M_CANDLE_REQUIRED", regime if isinstance(regime, str) else "UNKNOWN")
    if regime not in {"UPTREND", "DOWNTREND", "RANGE"}:
        return _blocked("REGIME_UNKNOWN_OR_UNSUPPORTED", "UNKNOWN")
    observed = _parse_aware(observed_at)
    current = _parse_aware(now)
    if observed is None or current is None:
        return _blocked("TIME_EVIDENCE_INVALID", regime)
    age = (current - observed).total_seconds()
    if age < 0 or age > MAX_AGE_SECONDS:
        return _blocked("CLOSED_15M_CONTEXT_STALE_OR_FUTURE", regime)
    if not isinstance(feature_evidence, Mapping):
        return _blocked("FEATURE_EVIDENCE_INVALID", regime)

    eligible = []
    rejected = {}
    for family_id, profile in FAMILIES.items():
        if regime not in profile["regimes"]:
            rejected[family_id] = ["REGIME_NOT_COMPATIBLE"]
            continue
        missing, failed = [], []
        for feature_name in profile["features"]:
            item = feature_evidence.get(feature_name)
            if not isinstance(item, Mapping):
                missing.append(feature_name)
                continue
            if item.get("value") is not True and item.get("value") is not False:
                missing.append(feature_name)
                continue
            ref = item.get("evidence_ref")
            stamp = _parse_aware(item.get("observed_at"))
            if not isinstance(ref, str) or not ref.strip() or stamp != observed:
                missing.append(feature_name)
                continue
            if item["value"] is False:
                failed.append(feature_name)
        if missing:
            rejected[family_id] = ["FEATURE_EVIDENCE_MISSING_OR_UNBOUND:" + ",".join(missing)]
        elif failed:
            rejected[family_id] = ["REQUIRED_RESEARCH_FEATURE_FALSE:" + ",".join(failed)]
        else:
            eligible.append({
                "family_id": family_id, "family_version": profile["version"],
                "lifecycle": "RESEARCH_ONLY_NOT_ACTIVE",
                "required_features": list(profile["features"]),
                "setup_timeframe": SETUP_TIMEFRAME,
                "precision_timeframe": PRECISION_TIMEFRAME,
                "candidate_generation_authorized": False,
                "confirmation_approved": False, "risk_approved": False,
                "execution_enabled": False, "orders_placed": False,
            })
    return {
        "schema": SCHEMA, "version": VERSION, "status": "RESEARCH_DISPATCHED" if eligible else "NO_RESEARCH_FAMILY_ELIGIBLE",
        "reason_codes": [] if eligible else ["NO_FAMILY_MET_PREREGISTERED_RESEARCH_CONTEXT"],
        "source": SOURCE, "symbol": SYMBOL, "setup_timeframe": SETUP_TIMEFRAME,
        "regime": regime, "observed_at": observed.isoformat(),
        "research_eligible_families": eligible, "family_rejections": rejected,
        "daily_signal_limit_is_not_a_quota": True,
        "candidate_generation_authorized": False,
        "confirmation_approved": False, "risk_approved": False,
        "family_live_activation": False, "execution_enabled": False,
        "orders_placed": False,
    }