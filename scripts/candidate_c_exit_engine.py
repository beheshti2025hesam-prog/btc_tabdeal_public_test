"""Deterministic research-only bar exit resolution for Candidate C-v1.

This helper does not run OOS or place orders. It resolves one already-open
position against one OHLC bar using the frozen conservative SL-first policy.
"""
import math

POLICY_ID = "CONSERVATIVE_WORST_CASE_SL_FIRST"

def resolve_bar_exit(side, bar, stop_price, target_price):
    """Return a deterministic exit record, or None when neither level is touched.

    OHLC cannot reveal intrabar order. If both thresholds are touched in one
    bar, stop-loss wins. Prices are threshold prices; gap/slippage modeling is
    intentionally outside this helper and must be separately specified.
    """
    if side not in ("long", "short"):
        raise ValueError("FAIL_CLOSED: side must be long or short")
    try:
        high, low = float(bar["high"]), float(bar["low"])
        stop, target = float(stop_price), float(target_price)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("FAIL_CLOSED: malformed OHLC or exit levels") from exc
    if not all(map(math.isfinite, (high, low, stop, target))) or high < low:
        raise ValueError("FAIL_CLOSED: invalid OHLC or non-finite exit level")
    if side == "long":
        stop_hit, target_hit = low <= stop, high >= target
    else:
        stop_hit, target_hit = high >= stop, low <= target
    if stop_hit:
        return {"exit_reason": "stop_loss", "exit_price": stop,
                "policy_id": POLICY_ID,
                "same_bar_ambiguity": bool(target_hit)}
    if target_hit:
        return {"exit_reason": "take_profit", "exit_price": target,
                "policy_id": POLICY_ID, "same_bar_ambiguity": False}
    return None
