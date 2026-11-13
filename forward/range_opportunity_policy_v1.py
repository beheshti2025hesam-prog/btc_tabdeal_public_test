"""Research-only, forward-only range-reversion candidate policy.

Isolated from active Strategy V2. Emits candidates only after a closed 15m
sweep-and-reclaim at a prior range boundary; never confirms, sizes, or executes.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import math

POLICY_VERSION = "hes-range-sweep-reclaim-v1.2.0-research"

@dataclass(frozen=True)
class RangeSnapshot:
    symbol: str
    timeframe: str
    candle_closed: bool
    observed_at: datetime
    open: float
    high: float
    low: float
    close: float
    prior_range_high: float
    prior_range_low: float
    atr14: float
    adx14: float
    adx14_1h: float
    adx14_4h: float
    range_persistence: float
    ema50_slope_atr_1h: float
    ema50_slope_atr_4h: float
    rsi14_previous: float
    rsi14: float
    mfi14_previous: float
    mfi14: float
    estimated_round_trip_cost_fraction: float

@dataclass(frozen=True)
class RangeCandidate:
    policy_version: str
    state: str
    direction: str
    entry_reference: float | None
    stop_loss: float | None
    take_profit: float | None
    gross_rr: float | None
    net_rr_estimate: float | None
    reasons: tuple[str, ...]
    execution_enabled: bool = False
    orders_placed: bool = False


def _no(*reasons: str) -> RangeCandidate:
    return RangeCandidate(POLICY_VERSION, "NO_CANDIDATE", "NONE", None, None, None, None, None, tuple(reasons))


def evaluate_range_candidate(x: RangeSnapshot) -> RangeCandidate:
    """Evaluate one completed 15m candle using prior-only range boundaries.

    A range must persist across 15m observations, show subdued ADX on 15m/1h/4h,
    and lack material 1h/4h EMA50 slope. Entry requires a wick sweep, close back
    inside the prior range, RSI threshold recross, and MFI reversal. The first
    target is the range midpoint; stop is beyond the sweep extreme plus 0.15 ATR.
    """
    if x.symbol != "BTC_USDT" or x.timeframe != "15m": return _no("SCOPE_MISMATCH")
    if x.candle_closed is not True: return _no("CANDLE_NOT_CLOSED")
    if not isinstance(x.observed_at, datetime) or x.observed_at.tzinfo is None or x.observed_at.utcoffset() is None:
        return _no("OBSERVATION_TIME_NOT_TIMEZONE_AWARE")
    nums=(x.open,x.high,x.low,x.close,x.prior_range_high,x.prior_range_low,x.atr14,x.adx14,
          x.adx14_1h,x.adx14_4h,x.range_persistence,x.ema50_slope_atr_1h,x.ema50_slope_atr_4h,
          x.rsi14_previous,x.rsi14,x.mfi14_previous,x.mfi14,x.estimated_round_trip_cost_fraction)
    if not all(type(v) in (int,float) and math.isfinite(v) for v in nums): return _no("INVALID_OR_NON_FINITE_FEATURE")
    if min(x.open,x.high,x.low,x.close,x.prior_range_high,x.prior_range_low,x.atr14)<=0: return _no("NON_POSITIVE_PRICE_OR_ATR")
    if x.high<max(x.open,x.close,x.low) or x.low>min(x.open,x.close,x.high): return _no("INVALID_OHLC_GEOMETRY")
    if x.prior_range_high<=x.prior_range_low: return _no("INVALID_PRIOR_RANGE")
    if not 0<=x.range_persistence<=1 or x.estimated_round_trip_cost_fraction<0: return _no("INVALID_QUALITY_OR_COST")
    width=x.prior_range_high-x.prior_range_low; width_atr=width/x.atr14
    if not 2.0<=width_atr<=12.0: return _no("RANGE_WIDTH_OUT_OF_BOUNDS")
    if x.adx14>=25 or x.adx14_1h>=25 or x.adx14_4h>=25: return _no("TREND_STRENGTH_TOO_HIGH")
    if x.range_persistence<0.70: return _no("RANGE_NOT_PERSISTENT")
    if abs(x.ema50_slope_atr_1h)>0.50 or abs(x.ema50_slope_atr_4h)>0.50: return _no("HTF_DIRECTIONAL_PRESSURE")
    body=max(abs(x.close-x.open),x.atr14*0.02)
    lower_wick=min(x.open,x.close)-x.low; upper_wick=x.high-max(x.open,x.close)
    long_reclaim=(x.low<x.prior_range_low and x.close>x.prior_range_low and lower_wick>=1.25*body
                  and x.close<=x.prior_range_low+0.30*width and x.rsi14<40 and x.rsi14>x.rsi14_previous
                  and x.mfi14>x.mfi14_previous)
    short_reclaim=(x.high>x.prior_range_high and x.close<x.prior_range_high and upper_wick>=1.25*body
                   and x.close>=x.prior_range_high-0.30*width and x.rsi14>60 and x.rsi14<x.rsi14_previous
                   and x.mfi14<x.mfi14_previous)
    if long_reclaim==short_reclaim: return _no("NO_UNAMBIGUOUS_BOUNDARY_RECLAIM")
    entry=x.close; buffer=0.15*x.atr14; midpoint=(x.prior_range_high+x.prior_range_low)/2
    if long_reclaim:
        stop=x.low-buffer; target=midpoint; direction="LONG"
        if not stop<entry<target: return _no("INVALID_LONG_RANGE_GEOMETRY")
    else:
        stop=x.high+buffer; target=midpoint; direction="SHORT"
        if not target<entry<stop: return _no("INVALID_SHORT_RANGE_GEOMETRY")
    risk=abs(entry-stop); reward=abs(target-entry); gross_rr=reward/risk
    cost=entry*x.estimated_round_trip_cost_fraction; net_reward=reward-cost; net_rr=net_reward/(risk+cost)
    if net_reward<=0 or net_rr<1.20: return _no("NET_REWARD_TO_RISK_BELOW_FLOOR")
    return RangeCandidate(POLICY_VERSION,"CANDIDATE",direction,entry,stop,target,round(gross_rr,6),round(net_rr,6),
        ("PERSISTENT_RANGE","LOW_ADX_15M_1H_4H","LOW_HTF_EMA50_SLOPE","SWEEP_RECLAIM","MOMENTUM_REVERSAL","NET_RR_PASSED"))
