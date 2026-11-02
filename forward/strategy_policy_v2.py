"""HES experimental, fail-closed, forward-only BTC_USDT strategy policy v2.

Read-only policy: creates candidates only; does not place orders.
Thresholds are preregistered for evaluation, not claimed profitable.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict
from typing import Any, Mapping

POLICY_VERSION = "hes-btcusdt-mtf-confirmed-breakout-v2.0.0"
REQUIRED_TIMEFRAMES = ("15m", "1h", "4h")
NUMERIC_FEATURES = ("close", "ema50", "ema200", "atr14", "rsi14", "mfi14", "vwap20")


@dataclass(frozen=True)
class PolicyDecision:
    policy_version: str
    decision: str
    direction: str
    quality_score: int
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    rr: float | None
    reasons: tuple[str, ...]
    checks: Mapping[str, str]
    execution_enabled: bool = False
    orders_placed: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reasons"] = list(self.reasons)
        return d


def _is_finite_number(value: Any) -> bool:
    # bool is an int subclass in Python; never accept it as market/risk data.
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def evaluate(
    features: Mapping[str, Mapping[str, Any]],
    *,
    risk_fraction: float = 0.005,
    min_rr: float = 3.0,
) -> PolicyDecision:
    """Require aligned HTF trend, 15m close-confirmed breakout and independent flow/momentum.

    Missing/invalid values fail closed. Stops use 1.5x ATR; target is >=3R.
    risk_fraction is documented for later sizing, not used to submit orders.
    """
    if not isinstance(features, Mapping) or set(REQUIRED_TIMEFRAMES) - set(features):
        return PolicyDecision(
            POLICY_VERSION, "NO_TRADE", "NONE", 0, None, None, None, None,
            ("MISSING_OR_INVALID_TIMEFRAME",), {"data": "FAIL"},
        )

    checks: dict[str, str] = {}
    reasons: list[str] = []
    try:
        vals = []
        for tf in REQUIRED_TIMEFRAMES:
            f = features[tf]
            if not isinstance(f, Mapping):
                raise ValueError("INVALID_FEATURE_MAP_" + tf)
            if f.get("candle_closed") is not True:
                raise ValueError("CANDLE_NOT_CLOSED_" + tf)
            for key in NUMERIC_FEATURES:
                value = f.get(key)
                if not _is_finite_number(value):
                    raise ValueError("INVALID_" + key + "_" + tf)
            if f["close"] <= 0 or f["atr14"] <= 0:
                raise ValueError("INVALID_PRICE_OR_ATR_" + tf)
            if not 0 <= f["rsi14"] <= 100 or not 0 <= f["mfi14"] <= 100:
                raise ValueError("INDICATOR_OUT_OF_RANGE_" + tf)
            vals.append(f)

        if not _is_finite_number(risk_fraction) or not 0 < risk_fraction <= 0.01:
            raise ValueError("RISK_FRACTION_OUT_OF_RANGE")
        if not _is_finite_number(min_rr) or min_rr < 3.0:
            raise ValueError("RR_BELOW_POLICY_FLOOR_OR_INVALID")
    except (TypeError, ValueError, KeyError) as e:
        return PolicyDecision(
            POLICY_VERSION, "NO_TRADE", "NONE", 0, None, None, None, None,
            (str(e),), {"data": "FAIL"},
        )

    f15, f1, f4 = (features[x] for x in REQUIRED_TIMEFRAMES)
    long_htf = f1["ema50"] > f1["ema200"] and f4["ema50"] > f4["ema200"]
    short_htf = f1["ema50"] < f1["ema200"] and f4["ema50"] < f4["ema200"]
    checks["htf_trend"] = "PASS" if long_htf or short_htf else "FAIL"
    direction = "LONG" if long_htf else "SHORT" if short_htf else "NONE"
    if direction == "NONE":
        reasons.append("HTF_TREND_NOT_ALIGNED")

    breakout = f15.get("close_breakout20")
    breakout_ok = (direction == "LONG" and breakout == "UP") or (
        direction == "SHORT" and breakout == "DOWN"
    )
    checks["closed_breakout"] = "PASS" if breakout_ok else "FAIL"
    if not breakout_ok:
        reasons.append("NO_CONFIRMED_20_BAR_BREAKOUT")

    price_side = (
        direction == "LONG"
        and f15.get("close_vs_ema50") == "ABOVE"
        and f15.get("close_vs_vwap20") == "ABOVE"
    ) or (
        direction == "SHORT"
        and f15.get("close_vs_ema50") == "BELOW"
        and f15.get("close_vs_vwap20") == "BELOW"
    )
    checks["price_location"] = "PASS" if price_side else "FAIL"
    if not price_side:
        reasons.append("PRICE_NOT_ALIGNED_WITH_EMA50_AND_VWAP")

    rsi, mfi = float(f15["rsi14"]), float(f15["mfi14"])
    momentum = (
        direction == "LONG" and 55 <= rsi <= 75 and mfi > 55
    ) or (
        direction == "SHORT" and 25 <= rsi <= 45 and mfi < 45
    )
    checks["momentum_flow"] = "PASS" if momentum else "FAIL"
    if not momentum:
        reasons.append("MOMENTUM_OR_FLOW_NOT_CONFIRMED")

    # Every independent gate must pass; no weighted score overrides a failed gate.
    passed = sum(value == "PASS" for value in checks.values())
    quality = round(100 * passed / len(checks))
    if passed != len(checks):
        return PolicyDecision(
            POLICY_VERSION, "NO_TRADE", "NONE", quality, None, None, None, None,
            tuple(reasons or ["GATE_FAILED"]), checks,
        )

    entry = float(f15["close"])
    atr = float(f15["atr14"])
    stop_dist = 1.5 * atr
    if direction == "LONG":
        stop, target = entry - stop_dist, entry + min_rr * stop_dist
    else:
        stop, target = entry + stop_dist, entry - min_rr * stop_dist
    if not all(_is_finite_number(x) for x in (entry, stop, target, min_rr)):
        return PolicyDecision(
            POLICY_VERSION, "NO_TRADE", "NONE", quality, None, None, None, None,
            ("NON_FINITE_RISK_GEOMETRY",), checks,
        )
    if stop <= 0 or (
        direction == "LONG" and not stop < entry < target
    ) or (
        direction == "SHORT" and not target < entry < stop
    ):
        return PolicyDecision(
            POLICY_VERSION, "NO_TRADE", "NONE", quality, None, None, None, None,
            ("INVALID_RISK_GEOMETRY",), checks,
        )
    return PolicyDecision(
        POLICY_VERSION, direction, direction, quality, entry, stop, target, min_rr,
        ("ALL_POLICY_GATES_PASSED",), checks,
    )
