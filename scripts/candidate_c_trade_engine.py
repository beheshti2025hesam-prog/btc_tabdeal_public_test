"""Deterministic research-only Candidate C trade state machine.

No tuning, promotion, wallet or live execution. The engine consumes already
aggregated 1-minute OHLC bars and one frozen policy.
"""
import math

POLICY_ID = "CONSERVATIVE_WORST_CASE_SL_FIRST"

def _finite(*xs):
    return all(math.isfinite(float(x)) for x in xs)

def evaluate_signal(bars, i):
    if i < 20:
        return None
    prior_high = max(float(b["high"]) for b in bars[i-20:i])
    prior_low = min(float(b["low"]) for b in bars[i-20:i])
    close = float(bars[i]["close"])
    ema20 = float(bars[i]["ema20"])
    ema50 = float(bars[i]["ema50"])
    if close > prior_high and ema20 > ema50:
        return "long"
    if close < prior_low and ema20 < ema50:
        return "short"
    return None

def open_position(side, entry_price, atr_value):
    if side not in ("long", "short") or not _finite(entry_price, atr_value) or atr_value <= 0:
        raise ValueError("FAIL_CLOSED: invalid entry or ATR")
    entry = float(entry_price)
    atr = float(atr_value)
    if side == "long":
        stop, target = entry - 1.5 * atr, entry + 2.0 * atr
    else:
        stop, target = entry + 1.5 * atr, entry - 2.0 * atr
    return {"side": side, "entry_price": entry, "stop_price": stop,
            "target_price": target, "entry_bar": None}

def resolve_bar_exit(position, bar, holding_bars):
    from candidate_c_exit_engine import resolve_bar_exit as resolve
    result = resolve(position["side"], {
        "open": bar["open"], "high": bar["high"], "low": bar["low"]
    }, position["stop_price"], position["target_price"])
    if result is not None:
        return result
    if holding_bars >= 30:
        return {
            "exit_reason": "time_exit",
            "exit_price": float(bar["close"]),
            "policy_id": POLICY_ID,
            "same_bar_ambiguity": False,
        }
    return None

def run_fold(bars, start, end):
    """Run one isolated test fold. Position state is reset at fold boundaries."""
    if not (0 <= start < end <= len(bars)):
        raise ValueError("FAIL_CLOSED: invalid fold range")
    trades = []
    position = None
    i = start
    while i < end:
        bar = bars[i]
        if position is None:
            side = evaluate_signal(bars, i)
            if side is not None and i + 1 < end:
                entry_bar = bars[i + 1]
                position = open_position(side, entry_bar["open"], bar["atr14"])
                position["entry_bar"] = i + 1
                position["signal_bar"] = i
                i += 1
                continue
        else:
            holding = i - position["entry_bar"] + 1
            result = resolve_bar_exit(position, bar, holding)
            if result is not None:
                if position["side"] == "long":
                    pnl = (result["exit_price"] - position["entry_price"]) / position["entry_price"]
                else:
                    pnl = (position["entry_price"] - result["exit_price"]) / position["entry_price"]
                trades.append({
                    "signal_bar": position["signal_bar"],
                    "entry_bar": position["entry_bar"],
                    "exit_bar": i,
                    "side": position["side"],
                    "entry_price": position["entry_price"],
                    "exit_price": result["exit_price"],
                    "exit_reason": result["exit_reason"],
                    "same_bar_ambiguity": result["same_bar_ambiguity"],
                    "pnl_gross": pnl,
                    "policy_id": result["policy_id"],
                })
                position = None
        i += 1
    # An open position at the fold boundary is deliberately discarded, never carried.
    return trades
