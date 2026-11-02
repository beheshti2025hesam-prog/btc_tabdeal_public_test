import importlib.util
from pathlib import Path
MODULE = Path(__file__).resolve().parents[2] / "forward" / "neutral_decision_outcomes_v1.py"
spec = importlib.util.spec_from_file_location("neutral_decision_outcomes_v1", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def candle(t, o, h, low, c):
    return {"source":"gateio_public_spot","symbol":"BTC_USDT","timeframe":"15m","closed":True,
            "open_time":t,"close_time":t+900,"open":o,"high":h,"low":low,"close":c,"volume":1}

def test_directionless_no_trade_is_not_mislabelled_as_missed_trade():
    candles=[candle(0,100,101,99,100),candle(900,100,102,99,101),candle(1800,101,103,100,102),candle(2700,102,104,101,103)]
    d={"event_id":"e1","observed_at":"1970-01-01T00:15:00+00:00","decision":"NO_TRADE","direction":"NONE","proposal_direction":"NONE","symbol":"BTC_USDT"}
    out=mod.evaluate_no_trade(d,candles,horizons={"30m":1800})[0]
    assert out["outcome_class"]=="DIRECTIONLESS_MARKET_CONTEXT"
    assert out["hypothetical_trade_outcome"] is None and out["close_change_pct"] is not None

def test_rejected_short_candidate_same_bar_is_ambiguous():
    candles=[candle(0,100,101,99,100),candle(900,100,101,99,100),candle(1800,100,106,88,103)]
    d={"event_id":"e2","observed_at":"1970-01-01T00:30:00+00:00","decision":"NO_TRADE","proposal_direction":"SHORT","proposal_entry":100,"proposal_stop_loss":105,"proposal_take_profit":90,"symbol":"BTC_USDT"}
    out=mod.evaluate_no_trade(d,candles,horizons={"15m":900})[0]
    assert out["outcome_class"]=="AMBIGUOUS_SAME_CANDLE" and out["gross_R"] is None

def test_not_matured_horizon_stays_pending():
    candles=[candle(0,100,101,99,100),candle(900,100,101,99,100)]
    d={"event_id":"e3","observed_at":"1970-01-01T00:15:00+00:00","decision":"NO_TRADE","direction":"NONE"}
    out=mod.evaluate_no_trade(d,candles,horizons={"4h":14400})[0]
    assert out["outcome_class"]=="PENDING" and out["horizon_complete"] is False

def test_invalid_candle_gap_fails_closed():
    try: mod.validate_candles([candle(0,100,101,99,100),candle(1800,100,101,99,100)])
    except ValueError as exc: assert "GAP_OR_DUPLICATE" in str(exc)
    else: raise AssertionError("gap must fail closed")

def test_costs_and_live_execution_are_never_invented_or_enabled():
    candles=[candle(0,100,101,99,100),candle(900,100,101,99,100),candle(1800,100,101,99,100),candle(2700,100,101,99,100)]
    d={"event_id":"e4","observed_at":"1970-01-01T00:15:00+00:00","decision":"NO_TRADE","direction":"NONE"}
    out=mod.evaluate_no_trade(d,candles,horizons={"30m":1800})[0]
    assert out["net_R"] is None and out["policy_mutation_enabled"] is False and out["execution_enabled"] is False
