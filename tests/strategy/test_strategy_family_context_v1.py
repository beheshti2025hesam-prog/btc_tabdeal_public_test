from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from forward.strategy_family_context_v1 import (
    CONTEXT_VERSION,
    SCHEMA,
    build_strategy_family_context,
    verify_strategy_family_context,
)


NOW = datetime(2026, 11, 4, 18, 0, tzinfo=timezone.utc)
BASE = dict(
    source="gateio_public_spot",
    symbol="BTC_USDT",
    timeframe="15m",
    direction="LONG",
    observed_at=NOW,
    candidate={"state": "CANDIDATE", "entry": 100.0, "stop": 98.0, "target": 104.0},
    gate_evidence={"structure": {"status": "OBSERVED"}, "confirmation": {"state": "UNCONFIRMED"},
                   "risk": {"state": "RISK_REJECTED"}},
)


@pytest.mark.parametrize("regime,direction,family,state", [
    ("UPTREND", "LONG", "trend_breakout", "CANDIDATE_LOCKED_NOT_ACTIVE"),
    ("DOWNTREND", "SHORT", "trend_breakout", "CANDIDATE_LOCKED_NOT_ACTIVE"),
    ("RANGE", "LONG", "range_mean_reversion", "RESEARCH_ONLY_NOT_ACTIVE"),
    ("RANGE", "SHORT", "range_mean_reversion", "RESEARCH_ONLY_NOT_ACTIVE"),
])
def test_context_preserves_family_identity_and_is_never_authority(regime, direction, family, state):
    context = build_strategy_family_context(**{**BASE, "direction": direction}, regime=regime)
    assert context["schema"] == SCHEMA
    assert context["context_version"] == CONTEXT_VERSION
    assert context["family_id"] == family
    assert context["family_activation_state"] == state
    for field in ("candidate_generation_authorized", "confirmation_approved",
                  "risk_approved", "execution_enabled", "orders_placed"):
        assert context[field] is False
    assert verify_strategy_family_context(context, now=NOW) == (True, None)


@pytest.mark.parametrize("changes,reason", [
    ({"source": "tabdeal"}, "FAMILY_CONTEXT_SCOPE_INVALID"),
    ({"symbol": "ETH_USDT"}, "FAMILY_CONTEXT_SCOPE_INVALID"),
    ({"timeframe": "1m"}, "FAMILY_CONTEXT_SCOPE_INVALID"),
    ({"regime": "UNKNOWN"}, "FAMILY_CONTEXT_NO_ROUTABLE_FAMILY"),
    ({"direction": "NONE"}, "FAMILY_CONTEXT_DIRECTION_INVALID"),
])
def test_builder_rejects_out_of_scope_or_unroutable_context(changes, reason):
    args = {**BASE, "regime": "RANGE", **changes}
    with pytest.raises(ValueError, match=reason):
        build_strategy_family_context(**args)


def test_directional_family_rejects_countertrend_direction():
    for regime, direction in (("UPTREND", "SHORT"), ("DOWNTREND", "LONG")):
        with pytest.raises(ValueError, match="FAMILY_CONTEXT_DIRECTION_REGIME_MISMATCH"):
            build_strategy_family_context(**{**BASE, "direction": direction}, regime=regime)


def test_verifier_rejects_rehashed_countertrend_direction_and_invalid_max_age():
    from forward.strategy_family_context_v1 import _canonical_hash
    context = build_strategy_family_context(**BASE, regime="UPTREND")
    tampered = deepcopy(context)
    tampered["direction"] = "SHORT"
    tampered.pop("context_sha256")
    tampered["context_sha256"] = _canonical_hash(tampered)
    assert verify_strategy_family_context(tampered, now=NOW)[1] == "FAMILY_CONTEXT_DIRECTION_REGIME_MISMATCH"
    assert verify_strategy_family_context(context, now=NOW, max_age_seconds=True)[1] == "FAMILY_CONTEXT_MAX_AGE_INVALID"


def test_builder_rejects_naive_time_missing_candidate_and_missing_evidence():
    for changes, reason in [
        ({"observed_at": datetime(2026, 11, 4, 18)}, "FAMILY_CONTEXT_TIME_NOT_TIMEZONE_AWARE"),
        ({"candidate": {}}, "FAMILY_CONTEXT_CANDIDATE_MISSING"),
        ({"gate_evidence": {}}, "FAMILY_CONTEXT_GATE_EVIDENCE_MISSING"),
    ]:
        with pytest.raises(ValueError, match=reason):
            build_strategy_family_context(**{**BASE, "regime": "RANGE", **changes})


def test_tampered_candidate_and_gate_evidence_are_detected():
    context = build_strategy_family_context(**BASE, regime="RANGE")
    for field in ("candidate", "gate_evidence"):
        tampered = deepcopy(context)
        tampered[field]["tampered"] = True
        assert verify_strategy_family_context(tampered, now=NOW)[1] == "FAMILY_CONTEXT_DIGEST_MISMATCH"


def test_authority_flag_cannot_be_enabled_even_with_recomputed_digest():
    context = build_strategy_family_context(**BASE, regime="RANGE")
    from forward.strategy_family_context_v1 import _canonical_hash
    tampered = deepcopy(context)
    tampered["execution_enabled"] = True
    tampered.pop("context_sha256")
    tampered["context_sha256"] = _canonical_hash(tampered)
    assert verify_strategy_family_context(tampered, now=NOW) == (
        False, "FAMILY_CONTEXT_AUTHORITY_BOUNDARY_VIOLATION"
    )


def test_expired_future_and_invalid_clock_are_rejected():
    context = build_strategy_family_context(**BASE, regime="RANGE")
    assert verify_strategy_family_context(context, now=NOW + timedelta(seconds=901))[1] == "FAMILY_CONTEXT_EXPIRED_OR_FUTURE"
    assert verify_strategy_family_context(context, now=NOW - timedelta(seconds=1))[1] == "FAMILY_CONTEXT_EXPIRED_OR_FUTURE"
    assert verify_strategy_family_context(context, now=datetime(2026, 11, 4, 18))[1] == "FAMILY_CONTEXT_TIME_INVALID"


def test_range_and_trend_profiles_remain_distinct_and_non_executable():
    trend = build_strategy_family_context(**BASE, regime="UPTREND")
    rang = build_strategy_family_context(**BASE, regime="RANGE")
    assert trend["family_version"] != rang["family_version"]
    assert trend["candidate_sha256"] == rang["candidate_sha256"]
    assert trend["execution_enabled"] is rang["execution_enabled"] is False


def test_builder_rejects_nested_candidate_scope_and_direction_mismatch():
    bad_candidates = [
        ({"state": "CANDIDATE_SHORT", "symbol": "BTC_USDT", "timeframe": "15m", "regime": "UPTREND"}, "FAMILY_CONTEXT_CANDIDATE_DIRECTION_MISMATCH"),
        ({"state": "CANDIDATE_LONG", "symbol": "ETH_USDT", "timeframe": "15m", "regime": "UPTREND"}, "FAMILY_CONTEXT_CANDIDATE_SYMBOL_MISMATCH"),
        ({"state": "CANDIDATE_LONG", "symbol": "BTC_USDT", "timeframe": "1m", "regime": "UPTREND"}, "FAMILY_CONTEXT_CANDIDATE_TIMEFRAME_MISMATCH"),
        ({"state": "CANDIDATE_LONG", "symbol": "BTC_USDT", "timeframe": "15m", "regime": "RANGE"}, "FAMILY_CONTEXT_CANDIDATE_REGIME_MISMATCH"),
    ]
    for candidate, reason in bad_candidates:
        with pytest.raises(ValueError, match=reason):
            build_strategy_family_context(**{**BASE, "candidate": candidate}, regime="UPTREND")


def test_builder_rejects_gate_structure_regime_mismatch():
    with pytest.raises(ValueError, match="FAMILY_CONTEXT_STRUCTURE_REGIME_MISMATCH"):
        build_strategy_family_context(**{**BASE, "gate_evidence": {"structure": {"regime": "DOWNTREND"}}}, regime="UPTREND")


def test_verifier_rejects_rehashed_nested_payload_mismatch_and_precision_layer_tampering():
    from forward.strategy_family_context_v1 import _canonical_hash
    context = build_strategy_family_context(**BASE, regime="UPTREND")
    tampered = deepcopy(context)
    tampered["candidate"]["state"] = "CANDIDATE_SHORT"
    tampered["candidate_sha256"] = _canonical_hash(tampered["candidate"])
    tampered.pop("context_sha256")
    tampered["context_sha256"] = _canonical_hash(tampered)
    assert verify_strategy_family_context(tampered, now=NOW)[1] == "FAMILY_CONTEXT_CANDIDATE_DIRECTION_MISMATCH"

    tampered = deepcopy(context)
    tampered["precision_timeframe"] = "5m"
    tampered.pop("context_sha256")
    tampered["context_sha256"] = _canonical_hash(tampered)
    assert verify_strategy_family_context(tampered, now=NOW)[1] == "FAMILY_CONTEXT_PRECISION_TIMEFRAME_MISMATCH"
