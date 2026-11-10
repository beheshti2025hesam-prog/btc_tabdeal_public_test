from datetime import datetime, timedelta, timezone

import pytest

from forward.strategy_family_research_dispatch_v1 import (
    FAMILIES, dispatch_research_families,
)

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def evidence(names, value=True, stamp=NOW):
    return {
        name: {"value": value, "evidence_ref": f"gateio://BTC_USDT/15m/{name}",
               "observed_at": stamp.isoformat()}
        for name in names
    }


def call(**overrides):
    args = {
        "source": "gateio_public_spot", "symbol": "BTC_USDT",
        "timeframe": "15m", "regime": "UPTREND", "closed_candle": True,
        "observed_at": NOW.isoformat(), "now": NOW.isoformat(),
        "feature_evidence": evidence(FAMILIES["trend_continuation"]["features"]),
    }
    args.update(overrides)
    return dispatch_research_families(**args)


def test_trend_continuation_is_research_eligible_but_never_authorized():
    result = call()
    assert result["status"] == "RESEARCH_DISPATCHED"
    assert [x["family_id"] for x in result["research_eligible_families"]] == ["trend_continuation"]
    assert result["candidate_generation_authorized"] is False
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False


def test_multiple_families_can_be_research_eligible_without_becoming_trades():
    names = set(FAMILIES["trend_continuation"]["features"]) | set(FAMILIES["breakout_retest"]["features"])
    result = call(feature_evidence=evidence(names))
    assert {x["family_id"] for x in result["research_eligible_families"]} == {
        "trend_continuation", "breakout_retest"
    }


def test_range_reversion_requires_range_regime_and_all_boundary_features():
    names = FAMILIES["range_reversion"]["features"]
    result = call(regime="RANGE", feature_evidence=evidence(names))
    assert [x["family_id"] for x in result["research_eligible_families"]] == ["range_reversion"]


def test_volatility_expansion_requires_compression_and_expansion_evidence():
    names = FAMILIES["volatility_expansion"]["features"]
    result = call(regime="RANGE", feature_evidence=evidence(names))
    assert [x["family_id"] for x in result["research_eligible_families"]] == ["volatility_expansion"]


@pytest.mark.parametrize("overrides,reason", [
    ({"source": "other"}, "NON_CANONICAL_SOURCE"),
    ({"symbol": "ETH_USDT"}, "SYMBOL_OUT_OF_SCOPE"),
    ({"timeframe": "1m"}, "PRECISION_1M_CANNOT_ORIGINATE_SETUP"),
    ({"timeframe": "5m"}, "SETUP_TIMEFRAME_INVALID"),
    ({"closed_candle": False}, "CLOSED_15M_CANDLE_REQUIRED"),
    ({"regime": "UNKNOWN"}, "REGIME_UNKNOWN_OR_UNSUPPORTED"),
    ({"observed_at": "2026-11-10T12:00:00"}, "TIME_EVIDENCE_INVALID"),
    ({"observed_at": (NOW + timedelta(minutes=16)).isoformat()}, "CLOSED_15M_CONTEXT_STALE_OR_FUTURE"),
])
def test_fail_closed_context_validation(overrides, reason):
    result = call(**overrides)
    assert result["status"] == "BLOCKED"
    assert result["reason_codes"] == [reason]
    assert result["research_eligible_families"] == []
    assert result["execution_enabled"] is False


def test_missing_or_mistimed_feature_evidence_cannot_dispatch():
    required = FAMILIES["trend_continuation"]["features"]
    incomplete = evidence(required[:-1])
    result = call(feature_evidence=incomplete)
    assert result["status"] == "NO_RESEARCH_FAMILY_ELIGIBLE"
    assert result["research_eligible_families"] == []
    mistimed = evidence(required, stamp=NOW - timedelta(minutes=1))
    result = call(feature_evidence=mistimed)
    assert result["research_eligible_families"] == []


def test_false_feature_rejects_only_that_family_not_other_eligible_family():
    names = set(FAMILIES["trend_continuation"]["features"]) | set(FAMILIES["breakout_retest"]["features"])
    data = evidence(names)
    data["trend_persistent"]["value"] = False
    result = call(feature_evidence=data)
    assert [x["family_id"] for x in result["research_eligible_families"]] == ["breakout_retest"]
    assert "trend_continuation" in result["family_rejections"]


def test_missing_feature_evidence_does_not_block_an_unrelated_family_if_complete():
    names = FAMILIES["breakout_retest"]["features"]
    result = call(feature_evidence=evidence(names))
    assert [x["family_id"] for x in result["research_eligible_families"]] == ["breakout_retest"]