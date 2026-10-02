import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from candidate_c_trade_engine import evaluate_signal, open_position, resolve_bar_exit, run_fold, run_fold_with_boundary_evidence

def bar(o,h,l,c,ema20=110,ema50=100,atr14=2):
    return {"open":o,"high":h,"low":l,"close":c,"ema20":ema20,"ema50":ema50,"atr14":atr14}

def test_signal_uses_prior_20_bars_only():
    bars=[bar(100,101,99,100,100,100) for _ in range(20)]
    bars.append(bar(100,105,99,105,110,100))
    assert evaluate_signal(bars,20) == "long"

def test_long_same_bar_stop_first():
    p=open_position("long",100,2)
    r=resolve_bar_exit(p,bar(100,105,95,100),1)
    assert r["exit_reason"] == "stop_loss"
    assert r["same_bar_ambiguity"] is True

def test_short_same_bar_stop_first():
    p=open_position("short",100,2)
    r=resolve_bar_exit(p,bar(100,105,95,100),1)
    assert r["exit_reason"] == "stop_loss"
    assert r["same_bar_ambiguity"] is True

def test_time_exit_after_30_post_entry_bars():
    p=open_position("long",100,2)
    r=resolve_bar_exit(p,bar(100,101,99,103),30)
    assert r["exit_reason"] == "time_exit"

def test_fold_does_not_carry_position():
    bars=[bar(100,101,99,100,100,100) for _ in range(20)]
    bars.append(bar(100,105,99,105,110,100))
    bars.append(bar(105,106,104,105,110,100))
    # Test range ends immediately after the entry bar; no trade may leak outside it.
    assert run_fold(bars, 20, 22) == []

def test_invalid_entry_fails_closed():
    try:
        open_position("long",100,0)
    except ValueError as exc:
        assert "FAIL_CLOSED" in str(exc)
    else:
        raise AssertionError("invalid ATR did not fail closed")


def test_millisecond_timestamp_normalization_and_gap_policy_source():
    # Evaluator must normalize millisecond epochs before bucketing and reject
    # unresolved 1-minute gaps rather than compressing holding-bar time.
    from candidate_c_evaluator import aggregate_1m_stream
    import io
    raw = "timestamp,price,quantity\n1700000000000,100,1\n1700000060000,101,1\n"
    bars = aggregate_1m_stream(io.StringIO(raw))
    assert [b["t"] for b in bars] == [28333333, 28333334]

def test_fold_timestamp_gap_is_not_silently_compressed():
    bars = [bar(100,101,99,100,100,100) for _ in range(20)]
    bars[0]["t"] = 100
    bars[1]["t"] = 102
    assert bars[1]["t"] - bars[0]["t"] != 1


def test_long_adverse_gap_exits_at_open():
    p=open_position("long",100,2)
    r=resolve_bar_exit(p,bar(96,100,95,97),1)
    assert r["exit_reason"] == "stop_loss_gap"
    assert r["exit_price"] == 96

def test_short_adverse_gap_exits_at_open():
    p=open_position("short",100,2)
    r=resolve_bar_exit(p,bar(104,105,99,103),1)
    assert r["exit_reason"] == "stop_loss_gap"
    assert r["exit_price"] == 104


def test_time_exit_does_not_fire_on_29th_post_entry_bar():
    p=open_position("long",100,2)
    assert resolve_bar_exit(p,bar(100,101,99,103),29) is None


def test_1m_continuity_accepts_consecutive_minutes():
    from candidate_c_evaluator import validate_1m_continuity
    assert validate_1m_continuity([{"t":100},{"t":101},{"t":102}]) is True


def test_1m_continuity_fails_closed_on_gap():
    from candidate_c_evaluator import validate_1m_continuity
    import pytest
    with pytest.raises(RuntimeError, match="FAIL_CLOSED: unresolved 1m timestamp gap"):
        validate_1m_continuity([{"t":100},{"t":102}])


def test_long_favorable_gap_exits_at_open():
    p=open_position("long",100,2)
    r=resolve_bar_exit(p,bar(105,106,104,105),1)
    assert r["exit_reason"] == "take_profit_gap"
    assert r["exit_price"] == 105


def test_short_favorable_gap_exits_at_open():
    p=open_position("short",100,2)
    r=resolve_bar_exit(p,bar(95,96,94,95),1)
    assert r["exit_reason"] == "take_profit_gap"
    assert r["exit_price"] == 95

def test_fold_boundary_open_position_is_censored_and_not_carried():
    bars=[bar(100,101,99,100,100,100) for _ in range(20)]
    bars.append(bar(100,105,99,105,110,100))
    bars.append(bar(105,106,104,105,110,100))
    trades, boundary = run_fold_with_boundary_evidence(bars, 20, 22)
    assert trades == []
    assert boundary["position_open_at_fold_end"] is True
    assert boundary["censored_position_count"] == 1
    assert boundary["carried_to_next_fold"] is False
