from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from forward.strategy_family_research_features_v1 import assess_strategy_families


def rows_fixture(breakout=False):
    start=1_794_000_000
    values=[]
    for i in range(80):
        close=100.0 + (0.15 if i%2 else -0.15)
        high=close+0.4
        low=close-0.4
        if breakout and i==78:
            close=103.0; high=103.4; low=100.0
        if breakout and i==79:
            close=101.5; high=102.0; low=100.0
        open_price=close
        values.append({
            "schema":"hes_global_candle_v1","source":"gateio_public_spot",
            "symbol":"BTC_USDT","timeframe":"15m","closed":True,
            "open_time":start+i*900,"close_time":start+(i+1)*900,
            "open":open_price,"high":high,"low":low,"close":close,
            "volume":100.0,"quote_volume":10000.0,
            "observed_at":datetime.fromtimestamp(start+(i+1)*900+1,timezone.utc).isoformat(),
            "trade_count":None,"taker_buy_volume":None,"taker_buy_quote_volume":None,
        })
    return values


def test_assessment_emits_all_four_families_as_research_only():
    rows=rows_fixture()
    observed=datetime.fromtimestamp(rows[-1]["close_time"],timezone.utc)
    result=assess_strategy_families(
        source="gateio_public_spot",symbol="BTC_USDT",timeframe="15m",
        regime="UPTREND",observed_at=observed,now=observed+timedelta(seconds=1),
        rows_15m=rows,
        structure={"status":"OBSERVED","events":["BOS_BULLISH"]},
        trend_candidate=SimpleNamespace(state="CANDIDATE_LONG"),
        range_evidence=SimpleNamespace(status="NO_CANDIDATE",candidate=None),
    )
    assert set(result["families"]) == {
        "trend_continuation","breakout_retest","range_reversion","volatility_expansion"
    }
    assert result["candle_window_sha256"]
    assert all(item["execution_enabled"] is False for item in result["families"].values())
    assert all(item["orders_placed"] is False for item in result["families"].values())
    assert result["candidate_generation_authorized"] is False


def test_breakout_retest_requires_closed_breakout_and_actual_retest():
    rows=rows_fixture(breakout=True)
    observed=datetime.fromtimestamp(rows[-1]["close_time"],timezone.utc)
    result=assess_strategy_families(
        source="gateio_public_spot",symbol="BTC_USDT",timeframe="15m",
        regime="UPTREND",observed_at=observed,now=observed+timedelta(seconds=1),
        rows_15m=rows,structure={"status":"OBSERVED","events":["BOS_BULLISH"]},
        trend_candidate=SimpleNamespace(state="NO_CANDIDATE"),
        range_evidence=SimpleNamespace(status="NO_CANDIDATE",candidate=None),
    )
    item=result["families"]["breakout_retest"]
    assert item["features"]["breakout_closed"] is True
    assert item["features"]["acceptance_outside_boundary"] is True
    assert item["features"]["retest_confirmed"] is True
    assert item["direction"] == "LONG"


def test_market_observation_time_is_distinct_from_the_closed_candle_boundary():
    rows=rows_fixture()
    close_boundary=datetime.fromtimestamp(rows[-1]["close_time"],timezone.utc)
    market_observed=close_boundary+timedelta(seconds=4)
    result=assess_strategy_families(
        source="gateio_public_spot",symbol="BTC_USDT",timeframe="15m",regime="UPTREND",
        observed_at=market_observed,now=market_observed+timedelta(seconds=1),rows_15m=rows,
        structure={},trend_candidate=None,range_evidence=None,
    )
    assert result["status"] == "ASSESSED"
    assert result["observed_at"] == close_boundary.isoformat()
    assert result["market_observed_at"] == market_observed.isoformat()


def test_stale_last_closed_15m_candle_blocks_research_assessment():
    rows=rows_fixture()
    close_boundary=datetime.fromtimestamp(rows[-1]["close_time"],timezone.utc)
    market_observed=close_boundary+timedelta(seconds=901)
    result=assess_strategy_families(
        source="gateio_public_spot",symbol="BTC_USDT",timeframe="15m",regime="UPTREND",
        observed_at=market_observed,now=market_observed+timedelta(seconds=1),rows_15m=rows,
        structure={},trend_candidate=None,range_evidence=None,
    )
    assert result["status"] == "BLOCKED"
    assert result["reason_codes"] == ["SETUP_CANDLE_STALE_OR_FUTURE"]


def test_research_assessment_fails_closed_on_missing_or_overlapping_15m_candles():
    rows=rows_fixture()
    midpoint=rows[len(rows)//2]
    midpoint["open_time"] += 900
    midpoint["close_time"] += 900
    observed=datetime.fromtimestamp(rows[-1]["close_time"],timezone.utc)
    result=assess_strategy_families(
        source="gateio_public_spot",symbol="BTC_USDT",timeframe="15m",regime="UPTREND",
        observed_at=observed,now=observed+timedelta(seconds=1),rows_15m=rows,
        structure={},trend_candidate=None,range_evidence=None,
    )
    assert result["status"] == "BLOCKED"
    assert result["reason_codes"] == ["CLOSED_15M_CANDLE_GAP_OR_OVERLAP"]
    assert result["research_eligible_family_ids"] == []
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False


def test_research_assessment_fails_closed_on_noncanonical_source_or_missing_rows():
    rows=rows_fixture()
    observed=datetime.fromtimestamp(rows[-1]["close_time"],timezone.utc)
    result=assess_strategy_families(
        source="tabdeal",symbol="BTC_USDT",timeframe="15m",regime="UPTREND",
        observed_at=observed,now=observed+timedelta(seconds=1),rows_15m=rows,
        structure={},trend_candidate=None,range_evidence=None,
    )
    assert result["status"] == "BLOCKED"
    assert result["execution_enabled"] is False
    result=assess_strategy_families(
        source="gateio_public_spot",symbol="BTC_USDT",timeframe="15m",regime="UPTREND",
        observed_at=observed,now=observed+timedelta(seconds=1),rows_15m=[],
        structure={},trend_candidate=None,range_evidence=None,
    )
    assert result["status"] == "BLOCKED"
    assert result["research_eligible_family_ids"] == []
    assert result["families"] == {}


def test_trend_continuation_requires_existing_provider_quorum_and_cost_geometry():
    from forward.strategy_family_research_features_v1 import assess_strategy_families
    rows=rows_fixture()
    observed=datetime.fromtimestamp(rows[-1]["close_time"],timezone.utc)
    checks=[
        SimpleNamespace(name="htf_trend_alignment",state="PASS"),
        SimpleNamespace(name="pullback_location",state="PASS"),
        SimpleNamespace(name="reversal_break_confirmation",state="PASS"),
        SimpleNamespace(name="mfi_confirmation",state="FAIL"),
        SimpleNamespace(name="adx_directional_strength",state="PASS"),
        SimpleNamespace(name="risk_geometry_3_to_1",state="PASS"),
    ]
    bundle=SimpleNamespace(direction="BULLISH",strategy_checks=checks,risk_geometry=(100.0,97.0,109.0))
    quality=SimpleNamespace(state="PASS")
    result=assess_strategy_families(
        source="gateio_public_spot",symbol="BTC_USDT",timeframe="15m",
        regime="UPTREND",observed_at=observed,now=observed+timedelta(seconds=1),
        rows_15m=rows,structure={"status":"OBSERVED","events":["BOS_BULLISH"]},
        trend_candidate=SimpleNamespace(state="CANDIDATE_LONG"),
        range_evidence=SimpleNamespace(status="NO_CANDIDATE",candidate=None),
        trend_evidence_bundle=bundle,trend_quality=quality,
    )
    trend=result["families"]["trend_continuation"]
    assert trend["status"]=="RESEARCH_ELIGIBLE"
    assert trend["features"]["mfi_confirmation"] is False  # the existing 5/6 policy allows MFI as its optional vote
    assert trend["diagnostics"]["cost_model_status"]=="ASSUMPTION_BASED"
    assert trend["candidate_generation_authorized"] is False
    result=assess_strategy_families(
        source="gateio_public_spot",symbol="BTC_USDT",timeframe="15m",
        regime="UPTREND",observed_at=observed,now=observed+timedelta(seconds=1),
        rows_15m=rows,structure={"status":"OBSERVED","events":["BOS_BULLISH"]},
        trend_candidate=SimpleNamespace(state="CANDIDATE_LONG"),
        range_evidence=SimpleNamespace(status="NO_CANDIDATE",candidate=None),
    )
    assert result["families"]["trend_continuation"]["status"]=="NOT_ELIGIBLE"


def test_cost_adjusted_geometry_requires_minimum_one_net_r_after_assumed_costs():
    from forward.strategy_family_research_features_v1 import _cost_geometry
    low_cost={"fee_fraction_per_side":0.0005,"slippage_fraction_per_side":0.0005}
    high_cost={"fee_fraction_per_side":0.006,"slippage_fraction_per_side":0.0}
    passed,net_rr=_cost_geometry(100.0,99.0,"LONG",low_cost)
    assert passed is True and net_rr is not None and net_rr >= 1.0
    passed,net_rr=_cost_geometry(100.0,99.0,"LONG",high_cost)
    assert passed is False and net_rr is not None and net_rr < 1.0
