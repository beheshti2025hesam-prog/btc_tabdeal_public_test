from forward.paper_outcome_resolver_v1 import resolve_paper_outcome


def candidate(direction="LONG"):
    return {
        "candidate_time": 1_700_000_000,
        "direction": direction,
        "stop_loss": 99 if direction == "LONG" else 101,
        "take_profit": 103 if direction == "LONG" else 97,
    }


def bar(close_time, *, high=102, low=100, close=101):
    return {"close_time": close_time, "high": high, "low": low, "close": close}


def test_shared_resolver_preserves_long_take_profit_behavior():
    result = resolve_paper_outcome(candidate(), [bar(1_700_000_900, high=104)])
    assert result == {
        "outcome": "wins", "reason": "TAKE_PROFIT",
        "exit_close_time": 1_700_000_900, "exit_close": 101,
        "exit_price": 103, "ambiguous_same_candle": False, "timeout": False,
    }


def test_shared_resolver_preserves_short_stop_behavior():
    result = resolve_paper_outcome(candidate("SHORT"), [bar(1_700_000_900, high=102)])
    assert result["outcome"] == "losses"
    assert result["reason"] == "STOP_LOSS"
    assert result["exit_price"] == 101


def test_shared_resolver_keeps_same_candle_conservative_loss():
    result = resolve_paper_outcome(candidate(), [bar(1_700_000_900, high=104, low=98)])
    assert result["outcome"] == "losses"
    assert result["ambiguous_same_candle"] is True
    assert result["reason"] == "STOP_AND_TARGET_SAME_CANDLE_CONSERVATIVE_LOSS"


def test_shared_resolver_keeps_24h_timeout_semantics():
    result = resolve_paper_outcome(candidate(), [
        bar(1_700_000_000 + 86_400, high=102, low=100, close=100.5)
    ])
    assert result["outcome"] == "timeouts"
    assert result["reason"] == "MAX_HOLD_24H"
    assert result["timeout"] is True
    assert result["exit_price"] == 100.5


def test_shared_resolver_returns_pending_when_no_exit_or_timeout_yet():
    assert resolve_paper_outcome(candidate(), [bar(1_700_000_900)]) is None
    assert resolve_paper_outcome(candidate(), []) is None


def test_shared_resolver_rejects_invalid_candidate_geometry():
    invalid = {**candidate(), "direction": "SIDEWAYS"}
    try:
        resolve_paper_outcome(invalid, [])
    except ValueError as exc:
        assert str(exc) == "PAPER_CANDIDATE_GEOMETRY_INVALID"
    else:
        raise AssertionError("invalid candidate was accepted")