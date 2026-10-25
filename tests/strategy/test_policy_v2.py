from forward.strategy_policy_v2 import evaluate, POLICY_VERSION


def base(tf, e50, e200, close, rsi, mfi, breakout, side):
    return {
        "candle_closed": True, "close": close, "ema50": e50, "ema200": e200,
        "atr14": 2.0, "rsi14": rsi, "mfi14": mfi,
        "vwap20": close - 1 if side == "ABOVE" else close + 1,
        "close_vs_ema50": side, "close_vs_vwap20": side, "close_breakout20": breakout,
    }


def aligned_long():
    return {
        "15m": base("15m", 110, 100, 120, 60, 65, "UP", "ABOVE"),
        "1h": base("1h", 110, 100, 120, 60, 65, "NONE", "ABOVE"),
        "4h": base("4h", 110, 100, 120, 60, 65, "NONE", "ABOVE"),
    }


def test_missing_timeframe_fails_closed():
    decision = evaluate({"15m": {}, "1h": {}})
    assert decision.decision == "NO_TRADE" and not decision.execution_enabled


def test_unknown_candle_fails_closed():
    features = aligned_long()
    features["15m"]["candle_closed"] = False
    assert evaluate(features).decision == "NO_TRADE"


def test_aligned_breakout_can_generate_policy_proposal_only():
    decision = evaluate(aligned_long())
    assert decision.decision == "LONG" and decision.rr >= 3
    assert decision.stop_loss < decision.entry < decision.take_profit
    assert decision.execution_enabled is False and decision.orders_placed is False
    assert decision.policy_version == POLICY_VERSION

def test_aligned_short_can_generate_policy_proposal_only():
    features = {
        "15m": base("15m", 90, 100, 80, 40, 35, "DOWN", "BELOW"),
        "1h": base("1h", 90, 100, 80, 40, 35, "NONE", "BELOW"),
        "4h": base("4h", 90, 100, 80, 40, 35, "NONE", "BELOW"),
    }
    decision = evaluate(features)
    assert decision.decision == "SHORT" and decision.rr >= 3
    assert decision.take_profit < decision.entry < decision.stop_loss
    assert decision.execution_enabled is False and decision.orders_placed is False


def test_conflicting_htf_blocks_signal():
    features = aligned_long()
    features["1h"] = base("1h", 90, 100, 120, 40, 35, "NONE", "BELOW")
    assert evaluate(features).decision == "NO_TRADE"


def test_momentum_failure_blocks_even_with_breakout():
    features = aligned_long()
    features["15m"]["rsi14"] = 49
    assert evaluate(features).decision == "NO_TRADE"


def test_invalid_atr_blocks_signal():
    features = aligned_long()
    features["15m"]["atr14"] = 0
    assert evaluate(features).decision == "NO_TRADE"


def test_risk_fraction_capped():
    assert evaluate(aligned_long(), risk_fraction=0.02).decision == "NO_TRADE"


def test_infinite_feature_fails_closed():
    features = aligned_long()
    features["15m"]["mfi14"] = float("inf")
    decision = evaluate(features)
    assert decision.decision == "NO_TRADE"
    assert "INVALID_mfi14_15m" in decision.reasons


def test_nonfinite_rr_fails_closed():
    decision = evaluate(aligned_long(), min_rr=float("inf"))
    assert decision.decision == "NO_TRADE"
    assert "RR_BELOW_POLICY_FLOOR_OR_INVALID" in decision.reasons


def test_nonfinite_risk_fraction_fails_closed():
    decision = evaluate(aligned_long(), risk_fraction=float("nan"))
    assert decision.decision == "NO_TRADE"
    assert "RISK_FRACTION_OUT_OF_RANGE" in decision.reasons
