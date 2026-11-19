"""Research-only, causal range-reversion strategy family for HES.

The engine consumes only closed Gate.io Spot candles. It identifies a persistent
range, requires two-sided boundary interaction and a sweep/reclaim reversal,
and estimates cost-adjusted geometry. It never authorizes a trade or execution.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from typing import Mapping, Sequence
from .universal_indicator_engine_v1 import OHLCVBar, calculate_indicators, normalize_bars

FAMILY_ID = "range_mean_reversion"
FAMILY_VERSION = "hes-range-mean-reversion-v2.0.0-research"
POLICY_ID = "HES_RANGE_BOUNDARY_SWEEP_RECLAIM_V2"
POLICY_VERSION = "2.0.0-research"
CANONICAL_SOURCE = "gateio_public_spot"
CANONICAL_SYMBOL = "BTC_USDT"
SETUP_TIMEFRAME = "15m"
MIN_BARS_15M = 220
MIN_BARS_HTF = 220
BOUNDARY_LOOKBACK = 64
BOUNDARY_LOW_QUANTILE = 0.10
BOUNDARY_HIGH_QUANTILE = 0.90
BOUNDARY_TOUCH_ATR = 0.35
MIN_TOUCHES_PER_SIDE = 2
MIN_TOUCH_SEPARATION_BARS = 12
MIN_RANGE_PERSISTENCE = 0.80
MIN_RANGE_WIDTH_ATR = 3.0
MAX_RANGE_WIDTH_ATR = 14.0
MIN_CHOPPINESS = 58.0
MAX_EFFICIENCY_RATIO = 0.25
MAX_ADX_15M = 23.0
MAX_ADX_HTF = 28.0
MAX_HTF_EMA50_SLOPE_ATR = 0.60
MIN_WICK_TO_BODY = 1.25
STOP_BUFFER_ATR = 0.15
MIN_NET_RR_RESEARCH = 1.20

@dataclass(frozen=True)
class CostModel:
    model_id: str
    round_trip_cost_fraction: float
    verified: bool = False

@dataclass(frozen=True)
class RangeCandidate:
    family_id: str
    family_version: str
    policy_id: str
    policy_version: str
    state: str
    direction: str
    observed_at: str
    entry_reference: float | None
    stop_loss: float | None
    take_profit: float | None
    gross_rr: float | None
    net_rr_estimate: float | None
    cost_model_id: str
    cost_model_verified: bool
    feature_snapshot: Mapping[str, float | int | str]
    reason_codes: tuple[str, ...]
    research_only: bool = True
    candidate_generation_authorized: bool = False
    confirmation_approved: bool = False
    risk_approved: bool = False
    execution_enabled: bool = False
    orders_placed: bool = False
    def as_dict(self) -> dict:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        result["feature_snapshot"] = dict(self.feature_snapshot)
        return result

def _no(reason: str, observed_at: datetime | None = None, cost_model_id: str = "UNSET",
        features: Mapping[str, float | int | str] | None = None) -> RangeCandidate:
    stamp = observed_at.astimezone(timezone.utc).isoformat() if isinstance(observed_at, datetime) and observed_at.tzinfo else ""
    return RangeCandidate(FAMILY_ID, FAMILY_VERSION, POLICY_ID, POLICY_VERSION, "NO_CANDIDATE",
        "NONE", stamp, None, None, None, None, None, cost_model_id, False,
        dict(features or {}), (reason,))

def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(float(v) for v in values)
    if not ordered: raise ValueError("EMPTY_PERCENTILE")
    pos = (len(ordered) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return ordered[lo] if lo == hi else ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)

def _ema_series(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period: return out
    current = sum(values[:period]) / period
    out[period - 1] = current
    alpha = 2.0 / (period + 1.0)
    for i in range(period, len(values)):
        current = values[i] * alpha + current * (1.0 - alpha)
        out[i] = current
    return out

def _valid_series(raw: Sequence[OHLCVBar], *, seconds: int, minimum: int,
                  observed_at: datetime) -> tuple[tuple[OHLCVBar, ...] | None, str | None]:
    if not isinstance(raw, Sequence) or len(raw) < minimum: return None, "INSUFFICIENT_CLOSED_CANDLES"
    if any(not isinstance(b, OHLCVBar) or b.closed is not True for b in raw): return None, "CLOSED_CANDLE_REQUIRED"
    try: bars = normalize_bars(raw)
    except (TypeError, ValueError, AttributeError): return None, "INVALID_CANDLE_SERIES"
    if len(bars) != len(raw): return None, "CLOSED_CANDLE_REQUIRED"
    if any(bars[i + 1].timestamp - bars[i].timestamp != seconds for i in range(len(bars) - 1)):
        return None, "CANDLE_GAP_OR_NONCANONICAL_CADENCE"
    if bars[-1].timestamp + seconds > int(observed_at.timestamp()): return None, "CANDLE_NOT_CLOSED_AT_OBSERVATION"
    if any(b.volume is None or b.quote_volume is None for b in bars): return None, "VENUE_VOLUME_FIELDS_MISSING"
    return bars, None

def _indicator(indicators: Mapping, name: str) -> float | None:
    item = indicators.get(name)
    value = getattr(item, "value", None)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)): return None
    return float(value)

def _indicators(bars: Sequence[OHLCVBar]) -> dict:
    return calculate_indicators(bars, volume_semantics_qualified=True)

def _htf_pressure(bars: Sequence[OHLCVBar], indicators: Mapping) -> tuple[float | None, float | None]:
    adx, atr = _indicator(indicators, "adx_14"), _indicator(indicators, "atr_14")
    ema = _ema_series([b.close for b in bars], 50)
    if atr is None or atr <= 0 or len(ema) < 5 or any(v is None for v in ema[-5:]): return adx, None
    return adx, abs(float(ema[-1]) - float(ema[-5])) / atr

def evaluate_range_strategy(*, source: str, symbol: str, timeframe: str,
    observed_at: datetime, bars_15m: Sequence[OHLCVBar], bars_1h: Sequence[OHLCVBar],
    bars_4h: Sequence[OHLCVBar], cost_model: CostModel) -> RangeCandidate:
    """Evaluate one closed 15m setup; 1m is intentionally downstream-only."""
    if source != CANONICAL_SOURCE or symbol != CANONICAL_SYMBOL or timeframe != SETUP_TIMEFRAME:
        return _no("SCOPE_MISMATCH")
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        return _no("OBSERVATION_TIME_NOT_TIMEZONE_AWARE")
    if not isinstance(cost_model, CostModel) or not isinstance(cost_model.model_id, str) or not cost_model.model_id.strip():
        return _no("COST_MODEL_REQUIRED")
    if isinstance(cost_model.round_trip_cost_fraction, bool) or not isinstance(cost_model.round_trip_cost_fraction, (int, float)) or not math.isfinite(float(cost_model.round_trip_cost_fraction)) or cost_model.round_trip_cost_fraction < 0:
        return _no("COST_MODEL_INVALID", observed_at, getattr(cost_model, "model_id", "UNSET"))
    observed_at = observed_at.astimezone(timezone.utc)
    s15, err = _valid_series(bars_15m, seconds=900, minimum=MIN_BARS_15M, observed_at=observed_at)
    if err: return _no(err, observed_at, cost_model.model_id)
    s1h, err = _valid_series(bars_1h, seconds=3600, minimum=MIN_BARS_HTF, observed_at=observed_at)
    if err: return _no("HTF_1H_" + err, observed_at, cost_model.model_id)
    s4h, err = _valid_series(bars_4h, seconds=14400, minimum=MIN_BARS_HTF, observed_at=observed_at)
    if err: return _no("HTF_4H_" + err, observed_at, cost_model.model_id)
    assert s15 is not None and s1h is not None and s4h is not None
    current = s15[-1]
    if current.timestamp + 900 != int(observed_at.timestamp()):
        return _no("OBSERVATION_NOT_BOUND_TO_LAST_15M_CLOSE", observed_at, cost_model.model_id)
    i15, i15_prev = _indicators(s15), _indicators(s15[:-1])
    i1h, i4h = _indicators(s1h), _indicators(s4h)
    atr, adx15 = _indicator(i15, "atr_14"), _indicator(i15, "adx_14")
    chop, er = _indicator(i15, "choppiness_14"), _indicator(i15, "efficiency_ratio_20")
    rsi, rsi_prev = _indicator(i15, "rsi_14"), _indicator(i15_prev, "rsi_14")
    mfi, mfi_prev = _indicator(i15, "mfi_14"), _indicator(i15_prev, "mfi_14")
    adx1h, slope1h = _htf_pressure(s1h, i1h)
    adx4h, slope4h = _htf_pressure(s4h, i4h)
    required = (atr, adx15, chop, er, rsi, rsi_prev, mfi, mfi_prev, adx1h, slope1h, adx4h, slope4h)
    if any(v is None for v in required) or atr is None or atr <= 0:
        return _no("CORE_RANGE_FEATURE_UNAVAILABLE", observed_at, cost_model.model_id)
    prior = s15[-(BOUNDARY_LOOKBACK + 1):-1]
    lower = _percentile([b.low for b in prior], BOUNDARY_LOW_QUANTILE)
    upper = _percentile([b.high for b in prior], BOUNDARY_HIGH_QUANTILE)
    width, width_atr = upper - lower, (upper - lower) / atr
    lower_touches = [i for i, b in enumerate(prior) if b.low <= lower + BOUNDARY_TOUCH_ATR * atr]
    upper_touches = [i for i, b in enumerate(prior) if b.high >= upper - BOUNDARY_TOUCH_ATR * atr]
    persistence = sum(lower - 0.25 * atr <= b.close <= upper + 0.25 * atr for b in prior) / len(prior)
    features = {
        "range_lower": lower, "range_upper": upper, "range_midpoint": (lower + upper) / 2.0,
        "range_width": width, "range_width_atr": width_atr,
        "lower_boundary_touches": len(lower_touches), "upper_boundary_touches": len(upper_touches),
        "range_persistence": persistence, "atr_14": atr, "adx_14_15m": adx15,
        "adx_14_1h": adx1h, "adx_14_4h": adx4h, "choppiness_14": chop,
        "efficiency_ratio_20": er, "ema50_slope_atr_1h": slope1h,
        "ema50_slope_atr_4h": slope4h, "rsi_14": rsi, "rsi_14_previous": rsi_prev,
        "mfi_14": mfi, "mfi_14_previous": mfi_prev,
    }
    if not MIN_RANGE_WIDTH_ATR <= width_atr <= MAX_RANGE_WIDTH_ATR:
        return _no("RANGE_WIDTH_OUT_OF_BOUNDS", observed_at, cost_model.model_id, features)
    if persistence < MIN_RANGE_PERSISTENCE:
        return _no("RANGE_PERSISTENCE_TOO_LOW", observed_at, cost_model.model_id, features)
    if len(lower_touches) < MIN_TOUCHES_PER_SIDE or len(upper_touches) < MIN_TOUCHES_PER_SIDE:
        return _no("INSUFFICIENT_TWO_SIDED_BOUNDARY_INTERACTION", observed_at, cost_model.model_id, features)
    if max(lower_touches) - min(lower_touches) < MIN_TOUCH_SEPARATION_BARS or max(upper_touches) - min(upper_touches) < MIN_TOUCH_SEPARATION_BARS:
        return _no("BOUNDARY_TOUCHES_NOT_PERSISTENT", observed_at, cost_model.model_id, features)
    if chop < MIN_CHOPPINESS or er > MAX_EFFICIENCY_RATIO:
        return _no("RANGE_CLASSIFIER_NOT_CONFIRMED", observed_at, cost_model.model_id, features)
    if adx15 >= MAX_ADX_15M or adx1h >= MAX_ADX_HTF or adx4h >= MAX_ADX_HTF:
        return _no("TREND_STRENGTH_TOO_HIGH", observed_at, cost_model.model_id, features)
    if slope1h > MAX_HTF_EMA50_SLOPE_ATR or slope4h > MAX_HTF_EMA50_SLOPE_ATR:
        return _no("HTF_DIRECTIONAL_PRESSURE", observed_at, cost_model.model_id, features)
    body = max(abs(current.close - current.open), atr * 0.02)
    lower_wick = min(current.open, current.close) - current.low
    upper_wick = current.high - max(current.open, current.close)
    midpoint = (lower + upper) / 2.0
    long_setup = (current.low < lower and current.close > lower
        and lower_wick >= MIN_WICK_TO_BODY * body
        and current.close <= lower + 0.30 * width
        and rsi < 45.0 and rsi > rsi_prev and mfi > mfi_prev and mfi < 60.0)
    short_setup = (current.high > upper and current.close < upper
        and upper_wick >= MIN_WICK_TO_BODY * body
        and current.close >= upper - 0.30 * width
        and rsi > 55.0 and rsi < rsi_prev and mfi < mfi_prev and mfi > 40.0)
    if long_setup == short_setup:
        return _no("NO_UNAMBIGUOUS_SWEEP_RECLAIM_REVERSAL", observed_at, cost_model.model_id, features)
    entry, buffer = current.close, STOP_BUFFER_ATR * atr
    if long_setup:
        direction, stop, target = "LONG", current.low - buffer, midpoint
        if not stop < entry < target: return _no("INVALID_LONG_RANGE_GEOMETRY", observed_at, cost_model.model_id, features)
    else:
        direction, stop, target = "SHORT", current.high + buffer, midpoint
        if not target < entry < stop: return _no("INVALID_SHORT_RANGE_GEOMETRY", observed_at, cost_model.model_id, features)
    risk, reward = abs(entry - stop), abs(target - entry)
    cost = entry * float(cost_model.round_trip_cost_fraction)
    gross_rr = reward / risk
    net_reward = reward - cost
    net_rr = net_reward / (risk + cost) if risk + cost > 0 else -math.inf
    features.update({"signal_open": current.open, "signal_high": current.high, "signal_low": current.low,
        "signal_close": current.close, "cost_fraction": float(cost_model.round_trip_cost_fraction),
        "estimated_round_trip_cost_price": cost, "gross_rr": gross_rr, "net_rr_estimate": net_rr})
    if net_reward <= 0 or net_rr < MIN_NET_RR_RESEARCH:
        return _no("COST_ADJUSTED_NET_RR_BELOW_RESEARCH_FLOOR", observed_at, cost_model.model_id, features)
    return RangeCandidate(FAMILY_ID, FAMILY_VERSION, POLICY_ID, POLICY_VERSION, "RESEARCH_CANDIDATE",
        direction, observed_at.isoformat(), entry, stop, target, round(gross_rr, 6), round(net_rr, 6),
        cost_model.model_id, bool(cost_model.verified), features,
        ("PERSISTENT_TWO_SIDED_RANGE", "LOW_TREND_STRENGTH_15M_1H_4H",
         "CHOP_ER_RANGE_CLASSIFIER", "HTF_EMA50_PRESSURE_CHECK",
         "BOUNDARY_SWEEP_AND_RECLAIM", "RSI_MFI_REVERSAL", "COST_ADJUSTED_GEOMETRY_PASSED"))


def build_range_family_context(candidate: RangeCandidate) -> dict:
    """Bind a Range research candidate to HES's shared, non-authorizing context envelope."""
    if not isinstance(candidate, RangeCandidate) or candidate.state != "RESEARCH_CANDIDATE":
        raise ValueError("RANGE_CONTEXT_RESEARCH_CANDIDATE_REQUIRED")
    if candidate.family_id != FAMILY_ID or candidate.family_version != FAMILY_VERSION:
        raise ValueError("RANGE_CONTEXT_FAMILY_VERSION_MISMATCH")
    observed_at = datetime.fromisoformat(candidate.observed_at.replace("Z", "+00:00"))
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("RANGE_CONTEXT_TIME_INVALID")
    from .strategy_family_context_v1 import build_strategy_family_context
    from .strategy_family_router_v1 import route_strategy_family
    route = route_strategy_family(source=CANONICAL_SOURCE, symbol=CANONICAL_SYMBOL,
        timeframe=SETUP_TIMEFRAME, regime="RANGE")
    if route.family_id != candidate.family_id or route.family_version != candidate.family_version:
        raise ValueError("RANGE_CONTEXT_ROUTER_PROFILE_MISMATCH")
    candidate_payload = {
        "symbol": CANONICAL_SYMBOL, "timeframe": SETUP_TIMEFRAME, "regime": "RANGE",
        "direction": candidate.direction, "observed_at": candidate.observed_at,
        "state": candidate.state, "entry": candidate.entry_reference,
        "stop_loss": candidate.stop_loss, "take_profit": candidate.take_profit,
        "gross_rr": candidate.gross_rr, "net_rr_estimate": candidate.net_rr_estimate,
        "family_id": candidate.family_id, "family_version": candidate.family_version,
        "policy_id": candidate.policy_id, "policy_version": candidate.policy_version,
        "reason_codes": list(candidate.reason_codes), "research_only": True,
        "candidate_generation_authorized": False,
    }
    gate_evidence = {
        "strategy_family_route": route.as_dict(),
        "range_strategy_engine": {
            "family_version": candidate.family_version,
            "policy_version": candidate.policy_version,
            "cost_model_id": candidate.cost_model_id,
            "cost_model_verified": candidate.cost_model_verified,
            "research_only": True,
            "candidate_generation_authorized": False,
            "execution_enabled": False,
            "orders_placed": False,
        },
    }
    return build_strategy_family_context(source=CANONICAL_SOURCE, symbol=CANONICAL_SYMBOL,
        timeframe=SETUP_TIMEFRAME, regime="RANGE", direction=candidate.direction,
        observed_at=observed_at, candidate=candidate_payload, gate_evidence=gate_evidence)
