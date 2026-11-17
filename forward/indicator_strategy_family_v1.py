"""Research-only indicator strategy family built on the validated universal indicator engine."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

FAMILY_ID = "indicator_strategy"
FAMILY_VERSION = "hes-indicator-strategy-family-v1.0.0"
VARIANTS = ("trend_confirmation", "momentum_breakout", "range_mean_reversion")
RR_TARGET = 3.0
STOP_ATR_MULTIPLE = 1.5

@dataclass(frozen=True)
class IndicatorCandidate:
    family_id: str
    family_version: str
    variant_id: str
    direction: str
    regime: str
    observed_at: int
    stop_distance: float
    target_distance: float
    reason_codes: tuple[str, ...]
    feature_snapshot: dict[str, Any]
    research_only: bool = True
    candidate_generation_authorized: bool = False
    decision_authority: bool = False
    risk_gate_bypass: bool = False
    execution_enabled: bool = False
    orders_placed: bool = False

def _v(snapshot, key):
    item = snapshot.indicators.get(key)
    return getattr(item, "value", None) if item is not None else None

def _aligned(snapshot, direction):
    regime = getattr(snapshot.regime, "label", "UNKNOWN")
    return regime == ("BULLISH" if direction == "LONG" else "BEARISH")

def evaluate_indicator_family(snapshot_15m, snapshot_1h, snapshot_4h, *, close: float):
    """Return at most one candidate per variant; never creates an order or overrides risk."""
    if snapshot_15m.timeframe != "15m" or snapshot_1h.timeframe != "1h" or snapshot_4h.timeframe != "4h":
        raise ValueError("INVALID_TIMEFRAME_ROLES")
    if any(s.data_status != "CLOSED_BARS_ONLY" or s.candle_count < 220 for s in (snapshot_15m,snapshot_1h,snapshot_4h)):
        return []
    regime = snapshot_15m.regime.label
    if regime in ("UNKNOWN", "TRANSITION"):
        return []
    atr = _v(snapshot_15m, "atr_14")
    if atr is None or atr <= 0 or close <= 0:
        return []
    candidates = []
    # Variant 1: trend confirmation. HTF direction must agree; indicators are conjunctive
    # predicates, not independent votes or a weighted probability.
    for direction in ("LONG", "SHORT"):
        htf_ok = _aligned(snapshot_1h,direction) and _aligned(snapshot_4h,direction)
        if not htf_ok or not _aligned(snapshot_15m,direction):
            continue
        ema20,ema50,ema200 = (_v(snapshot_15m,k) for k in ("ema_20","ema_50","ema_200"))
        adx,pdi,mdi,rsi,macd,st = (_v(snapshot_15m,k) for k in ("adx_14","plus_di_14","minus_di_14","rsi_14","macd_histogram","supertrend_direction"))
        if any(x is None for x in (ema20,ema50,ema200,adx,pdi,mdi,rsi,macd,st)):
            continue
        aligned = (ema20>ema50>ema200 and adx>=20 and pdi>mdi and 50<=rsi<=72 and macd>0 and st>0) if direction=="LONG" else (ema20<ema50<ema200 and adx>=20 and mdi>pdi and 28<=rsi<=50 and macd<0 and st<0)
        if aligned:
            candidates.append(_candidate("trend_confirmation",direction,regime,snapshot_15m,atr,{
                "ema_20":ema20,"ema_50":ema50,"ema_200":ema200,"adx_14":adx,"rsi_14":rsi,"macd_histogram":macd},
                ("HTF_ALIGNMENT","EMA_STACK","ADX_DMI_CONFIRMATION","MOMENTUM_CONFIRMATION","SUPERTREND_CONFIRMATION")))
    # Variant 2: momentum breakout. Current close must clear the prior (current-bar-excluded)
    # Donchian boundary; the HTF regime must agree.
    upper,lower = _v(snapshot_15m,"donchian_upper_prior"),_v(snapshot_15m,"donchian_lower_prior")
    adx,roc,macd = (_v(snapshot_15m,k) for k in ("adx_14","roc_10_pct","macd_histogram"))
    for direction in ("LONG","SHORT"):
        htf_ok = _aligned(snapshot_1h,direction) and _aligned(snapshot_4h,direction)
        broke = close>upper if direction=="LONG" and upper is not None else close<lower if direction=="SHORT" and lower is not None else False
        momentum = (roc is not None and macd is not None and adx is not None and
                    adx>=20 and ((roc>0 and macd>0) if direction=="LONG" else (roc<0 and macd<0)))
        if htf_ok and broke and momentum:
            candidates.append(_candidate("momentum_breakout",direction,regime,snapshot_15m,atr,
                {"donchian_reference":upper if direction=="LONG" else lower,"adx_14":adx,"roc_10_pct":roc,"macd_histogram":macd},
                ("HTF_ALIGNMENT","PRIOR_DONCHIAN_BREAK","ADX_CONFIRMATION","MOMENTUM_CONFIRMATION")))
    # Variant 3: range mean reversion. Require a confirmed RANGE regime on 15m and no
    # strongly directional HTF context; entries are evaluated at the next executable open.
    if regime=="RANGE" and snapshot_1h.regime.label not in ("BULLISH","BEARISH") and snapshot_4h.regime.label not in ("BULLISH","BEARISH"):
        pctb,rsi = _v(snapshot_15m,"bollinger_percent_b"),_v(snapshot_15m,"rsi_14")
        if pctb is not None and rsi is not None:
            if pctb<=0.05 and rsi<=32:
                candidates.append(_candidate("range_mean_reversion","LONG",regime,snapshot_15m,atr,
                    {"bollinger_percent_b":pctb,"rsi_14":rsi},("RANGE_REGIME","LOWER_BAND_EXTREME","RSI_OVERSOLD")))
            elif pctb>=0.95 and rsi>=68:
                candidates.append(_candidate("range_mean_reversion","SHORT",regime,snapshot_15m,atr,
                    {"bollinger_percent_b":pctb,"rsi_14":rsi},("RANGE_REGIME","UPPER_BAND_EXTREME","RSI_OVERBOUGHT")))
    return candidates

def _candidate(variant,direction,regime,snapshot,atr,features,reasons):
    stop_distance=float(atr)*STOP_ATR_MULTIPLE
    return IndicatorCandidate(FAMILY_ID,FAMILY_VERSION,variant,direction,regime,int(snapshot.as_of),
        stop_distance,stop_distance*RR_TARGET,tuple(reasons),dict(features))

def geometry(candidate: IndicatorCandidate, entry: float):
    if entry<=0: raise ValueError("INVALID_ENTRY")
    if candidate.direction=="LONG":
        stop,target=entry-candidate.stop_distance,entry+candidate.target_distance
        valid=0<stop<entry<target
    elif candidate.direction=="SHORT":
        stop,target=entry+candidate.stop_distance,entry-candidate.target_distance
        valid=0<target<entry<stop
    else: raise ValueError("INVALID_DIRECTION")
    rr=abs(target-entry)/abs(entry-stop) if valid else None
    if not valid or rr is None or rr+1e-12<RR_TARGET:
        return None
    return {"entry":float(entry),"stop_loss":float(stop),"take_profit":float(target),"rr":float(rr)}

def candidate_record(candidate, *, event_id, symbol, timeframe, entry=None, source="gateio_public_spot"):
    row={"schema":"hes_indicator_strategy_shadow_decision_v1","event_id":event_id,
         "observed_at":candidate.observed_at,"symbol":symbol,"timeframe":timeframe,
         "decision":candidate.direction,"direction":candidate.direction,"entry":entry,
         "strategy_family_id":candidate.family_id,"strategy_family_version":candidate.family_version,
         "strategy_variant_id":candidate.variant_id,"market_regime":candidate.regime,
         "reason_codes":list(candidate.reason_codes),"feature_snapshot":candidate.feature_snapshot,
         "evidence_source":source,"research_only":True,"performance_eligible":False,
         "outcome":None,"closed_at":None,"candidate_generation_authorized":False,
         "decision_authority":False,"risk_gate_bypass":False,"execution_enabled":False,"orders_placed":False}
    return row
