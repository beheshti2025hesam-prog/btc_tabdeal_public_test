from datetime import datetime, timezone
from math import sin
from types import SimpleNamespace
import json
import pytest

import forward.range_strategy_engine_v2 as engine
from forward.range_strategy_engine_v2 import CostModel, evaluate_range_strategy
from forward.universal_indicator_engine_v1 import OHLCVBar


def _series(count, seconds, end_close, base=100.0):
    first = end_close - count * seconds
    out, previous = [], base
    for i in range(count):
        close = base + 5.0 * sin(i * 0.25)
        op = previous
        high, low = max(op, close) + 0.8, min(op, close) - 0.8
        out.append(OHLCVBar(first + i * seconds, op, high, low, close, 10.0, close * 10.0, True))
        previous = close
    return out


def _inputs():
    observed = datetime.fromtimestamp(2_000_000_000, tz=timezone.utc)
    bars15 = _series(240, 900, int(observed.timestamp()))
    prior = bars15[-65:-1]
    lower = engine._percentile([b.low for b in prior], engine.BOUNDARY_LOW_QUANTILE)
    entry = lower + 1.0
    bars15[-1] = OHLCVBar(bars15[-1].timestamp, lower + 0.5, lower + 1.3,
        lower - 0.5, entry, 10.0, entry * 10.0, True)
    return (observed, bars15, _series(240, 3600, int(observed.timestamp())),
            _series(240, 14400, int(observed.timestamp())))


def _fake_indicators(bars, volume_semantics_qualified=True):
    step = bars[1].timestamp - bars[0].timestamp
    if step == 900:
        current = bars[-1].timestamp == 2_000_000_000 - 900
        values = {"atr_14": 2.0, "adx_14": 15.0, "choppiness_14": 65.0,
            "efficiency_ratio_20": 0.10, "rsi_14": 40.0 if current else 35.0,
            "mfi_14": 48.0 if current else 43.0}
    else:
        values = {"atr_14": 2.0, "adx_14": 15.0, "ema_50": 100.0}
    return {key: SimpleNamespace(value=value) for key, value in values.items()}


def _evaluate(monkeypatch, cost=0.0015, bars=None):
    observed, b15, b1h, b4h = bars or _inputs()
    monkeypatch.setattr(engine, "calculate_indicators", _fake_indicators)
    return evaluate_range_strategy(source="gateio_public_spot", symbol="BTC_USDT",
        timeframe="15m", observed_at=observed, bars_15m=b15, bars_1h=b1h,
        bars_4h=b4h, cost_model=CostModel("TEST_15BP", cost, False))


def test_range_engine_emits_research_only_long_candidate(monkeypatch):
    result = _evaluate(monkeypatch)
    assert result.state == "RESEARCH_CANDIDATE"
    assert result.direction == "LONG"
    assert result.net_rr_estimate >= engine.MIN_NET_RR_RESEARCH
    assert result.research_only is True
    assert result.candidate_generation_authorized is False
    assert result.confirmation_approved is False
    assert result.risk_approved is False
    assert result.execution_enabled is False
    assert result.orders_placed is False


def test_range_engine_rejects_costs_that_destroy_net_geometry(monkeypatch):
    result = _evaluate(monkeypatch, cost=0.05)
    assert result.state == "NO_CANDIDATE"
    assert result.reason_codes == ("COST_ADJUSTED_NET_RR_BELOW_RESEARCH_FLOOR",)


@pytest.mark.parametrize("source,symbol,timeframe", [
    ("tabdeal_broadcast", "BTC_USDT", "15m"),
    ("gateio_public_spot", "ETH_USDT", "15m"),
    ("gateio_public_spot", "BTC_USDT", "1m"),
])
def test_scope_is_fail_closed(monkeypatch, source, symbol, timeframe):
    observed, b15, b1h, b4h = _inputs()
    result = evaluate_range_strategy(source=source, symbol=symbol, timeframe=timeframe,
        observed_at=observed, bars_15m=b15, bars_1h=b1h, bars_4h=b4h,
        cost_model=CostModel("TEST", 0.001, False))
    assert result.state == "NO_CANDIDATE"
    assert result.reason_codes == ("SCOPE_MISMATCH",)


def test_unclosed_candle_is_rejected(monkeypatch):
    observed, b15, b1h, b4h = _inputs()
    b15[-1] = OHLCVBar(b15[-1].timestamp, b15[-1].open, b15[-1].high,
        b15[-1].low, b15[-1].close, 10, 1000, False)
    result = _evaluate(monkeypatch, bars=(observed, b15, b1h, b4h))
    assert result.reason_codes == ("CLOSED_CANDLE_REQUIRED",)


def test_15m_gap_is_rejected(monkeypatch):
    observed, b15, b1h, b4h = _inputs()
    del b15[100]
    result = _evaluate(monkeypatch, bars=(observed, b15, b1h, b4h))
    assert result.reason_codes == ("CANDLE_GAP_OR_NONCANONICAL_CADENCE",)


def test_future_or_not_yet_closed_htf_bar_is_rejected(monkeypatch):
    observed, b15, b1h, b4h = _inputs()
    b4h = [OHLCVBar(b.timestamp + 100, b.open, b.high, b.low, b.close, b.volume, b.quote_volume, True) for b in b4h]
    result = _evaluate(monkeypatch, bars=(observed, b15, b1h, b4h))
    assert result.reason_codes == ("HTF_4H_CANDLE_NOT_CLOSED_AT_OBSERVATION",)


def test_missing_cost_model_is_rejected():
    observed, b15, b1h, b4h = _inputs()
    result = evaluate_range_strategy(source="gateio_public_spot", symbol="BTC_USDT",
        timeframe="15m", observed_at=observed, bars_15m=b15, bars_1h=b1h,
        bars_4h=b4h, cost_model=None)
    assert result.reason_codes == ("COST_MODEL_REQUIRED",)


def test_invalid_cost_model_is_rejected():
    observed, b15, b1h, b4h = _inputs()
    result = evaluate_range_strategy(source="gateio_public_spot", symbol="BTC_USDT",
        timeframe="15m", observed_at=observed, bars_15m=b15, bars_1h=b1h,
        bars_4h=b4h, cost_model=CostModel("bad", float("nan"), False))
    assert result.reason_codes == ("COST_MODEL_INVALID",)


def test_trend_pressure_blocks_range_candidate(monkeypatch):
    observed, b15, b1h, b4h = _inputs()
    def trending(bars, volume_semantics_qualified=True):
        result = _fake_indicators(bars, volume_semantics_qualified)
        if bars[1].timestamp - bars[0].timestamp == 3600:
            result["adx_14"] = SimpleNamespace(value=35.0)
        return result
    monkeypatch.setattr(engine, "calculate_indicators", trending)
    result = evaluate_range_strategy(source="gateio_public_spot", symbol="BTC_USDT",
        timeframe="15m", observed_at=observed, bars_15m=b15, bars_1h=b1h,
        bars_4h=b4h, cost_model=CostModel("TEST", 0.0015, False))
    assert result.reason_codes == ("TREND_STRENGTH_TOO_HIGH",)


def test_no_ambiguous_or_double_sided_reversal(monkeypatch):
    observed, b15, b1h, b4h = _inputs()
    last = b15[-1]
    prior = b15[-65:-1]
    lower = engine._percentile([b.low for b in prior], engine.BOUNDARY_LOW_QUANTILE)
    b15[-1] = OHLCVBar(last.timestamp, last.open, last.high, lower + 0.1,
        last.close, last.volume, last.quote_volume, True)
    result = _evaluate(monkeypatch, bars=(observed, b15, b1h, b4h))
    assert result.state == "NO_CANDIDATE"


def test_candidate_record_is_json_safe_and_authority_fields_never_true(monkeypatch):
    payload = _evaluate(monkeypatch).as_dict()
    json.dumps(payload, allow_nan=False)
    for key in ("candidate_generation_authorized", "confirmation_approved",
        "risk_approved", "execution_enabled", "orders_placed"):
        assert payload[key] is False

def test_range_engine_emits_symmetric_research_only_short_candidate(monkeypatch):
    observed, b15, b1h, b4h = _inputs()
    prior = b15[-65:-1]
    upper = engine._percentile([b.high for b in prior], engine.BOUNDARY_HIGH_QUANTILE)
    entry = upper - 1.0
    last = b15[-1]
    b15[-1] = OHLCVBar(last.timestamp, upper - 0.5, upper + 0.5,
        upper - 1.3, entry, 10.0, entry * 10.0, True)
    def short_indicators(bars, volume_semantics_qualified=True):
        step = bars[1].timestamp - bars[0].timestamp
        if step == 900:
            current = bars[-1].timestamp == 2_000_000_000 - 900
            values = {"atr_14": 2.0, "adx_14": 15.0, "choppiness_14": 65.0,
                "efficiency_ratio_20": 0.10, "rsi_14": 60.0 if current else 65.0,
                "mfi_14": 52.0 if current else 57.0}
        else:
            values = {"atr_14": 2.0, "adx_14": 15.0, "ema_50": 100.0}
        return {key: SimpleNamespace(value=value) for key, value in values.items()}
    monkeypatch.setattr(engine, "calculate_indicators", short_indicators)
    result = evaluate_range_strategy(source="gateio_public_spot", symbol="BTC_USDT",
        timeframe="15m", observed_at=observed, bars_15m=b15, bars_1h=b1h,
        bars_4h=b4h, cost_model=CostModel("TEST_15BP", 0.0015, False))
    assert result.state == "RESEARCH_CANDIDATE"
    assert result.direction == "SHORT"
    assert result.execution_enabled is False and result.orders_placed is False


def test_missing_volume_semantics_fail_closed(monkeypatch):
    observed, b15, b1h, b4h = _inputs()
    last = b15[-1]
    b15[-1] = OHLCVBar(last.timestamp, last.open, last.high, last.low,
        last.close, None, None, True)
    result = _evaluate(monkeypatch, bars=(observed, b15, b1h, b4h))
    assert result.reason_codes == ("VENUE_VOLUME_FIELDS_MISSING",)


def test_real_universal_indicator_path_runs_without_monkeypatch():
    observed, b15, b1h, b4h = _inputs()
    result = evaluate_range_strategy(source="gateio_public_spot", symbol="BTC_USDT",
        timeframe="15m", observed_at=observed, bars_15m=b15, bars_1h=b1h,
        bars_4h=b4h, cost_model=CostModel("TEST_15BP", 0.0015, False))
    assert result.state in ("NO_CANDIDATE", "RESEARCH_CANDIDATE")
    assert result.execution_enabled is False and result.orders_placed is False

def test_candidate_binds_to_shared_family_context_without_authority(monkeypatch):
    from datetime import timedelta
    from forward.range_strategy_engine_v2 import build_range_family_context
    from forward.strategy_family_context_v1 import verify_strategy_family_context
    candidate = _evaluate(monkeypatch)
    context = build_range_family_context(candidate)
    observed = datetime.fromisoformat(candidate.observed_at)
    valid, reason = verify_strategy_family_context(context, now=observed + timedelta(seconds=1))
    assert valid is True and reason is None
    assert context["family_id"] == "range_mean_reversion"
    assert context["family_version"] == engine.FAMILY_VERSION
    assert context["family_activation_state"] == "RESEARCH_ONLY_NOT_ACTIVE"
    for key in ("candidate_generation_authorized", "confirmation_approved",
        "risk_approved", "execution_enabled", "orders_placed"):
        assert context[key] is False


def test_shared_context_rejects_non_candidate_state(monkeypatch):
    from dataclasses import replace
    from forward.range_strategy_engine_v2 import build_range_family_context
    candidate = _evaluate(monkeypatch)
    with pytest.raises(ValueError, match="RANGE_CONTEXT_RESEARCH_CANDIDATE_REQUIRED"):
        build_range_family_context(replace(candidate, state="NO_CANDIDATE"))

def test_frozen_policy_json_matches_engine_and_router_versions():
    from pathlib import Path
    import json
    from forward.strategy_family_router_v1 import RANGE_MEAN_REVERSION_RESEARCH_V2, ROUTER_VERSION
    policy = json.loads((Path(__file__).resolve().parents[2] / "forward/range_strategy_engine_v2.json").read_text())
    assert policy["policy_version"] == engine.POLICY_VERSION
    assert policy["family_version"] == engine.FAMILY_VERSION == RANGE_MEAN_REVERSION_RESEARCH_V2.version
    assert policy["router_version"] == ROUTER_VERSION
    assert policy["context_version"] == "hes-strategy-family-context-v1.1.0"
    for key in ("research_only", "candidate_generation_authorized", "confirmation_approved",
        "risk_approved", "execution_enabled", "orders_placed", "historical_tuning_allowed",
        "live_activation_allowed"):
        assert policy["controls"][key] is (key == "research_only")
