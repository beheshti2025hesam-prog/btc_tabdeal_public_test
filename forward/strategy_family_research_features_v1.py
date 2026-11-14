"""Causal four-family research assessment over persisted Gate.io 15m rows.

This module is diagnostic only. It reuses the existing Trend candidate and
Range evidence builder outputs supplied by the gate pipeline, and derives
Breakout/Retest + Volatility Expansion from the same closed OHLCV rows.
No network I/O, candidate authorization, confirmation, risk approval or orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from statistics import median
from pathlib import Path
from typing import Any, Mapping, Sequence

from .strategy_family_research_dispatch_v1 import FAMILIES, dispatch_research_families

SCHEMA = "hes_strategy_family_research_assessment_v1"
VERSION = "hes-strategy-family-research-assessment-v1.1.0"
SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"
TIMEFRAME = "15m"
MAX_AGE_SECONDS = 900
MIN_NET_RR_RESEARCH = 1.0


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _num(row: Mapping[str, Any], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or value is None:
        raise ValueError("INVALID_NUMERIC_FIELD:" + key)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("INVALID_NUMERIC_FIELD:" + key)
    if not math.isfinite(number):
        raise ValueError("INVALID_NUMERIC_FIELD:" + key)
    return number


def _aware(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("INVALID_OBSERVATION_TIME")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


def _load_cost_context() -> tuple[dict[str, Any] | None, str | None]:
    path = Path(__file__).with_name("paper_risk_context_v1.json")
    try:
        raw = path.read_bytes()
        config = json.loads(raw.decode("utf-8"))
        scope = config.get("scope", {})
        if (config.get("status") != "SIMULATION_ONLY_NOT_LIVE_APPROVAL"
                or scope.get("source") != SOURCE or scope.get("symbol") != SYMBOL
                or scope.get("timeframe") != TIMEFRAME
                or config.get("leverage") != 1
                or config.get("safety", {}).get("live_execution_enabled") is not False
                or config.get("safety", {}).get("orders_placed") is not False):
            return None, None
        for key in ("fee_fraction_per_side", "slippage_fraction_per_side"):
            raw_value = config.get(key)
            if type(raw_value) not in (int, float):
                return None, None
            value = float(raw_value)
            if not math.isfinite(value) or value < 0:
                return None, None
        return config, hashlib.sha256(raw).hexdigest()
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None, None


def _cost_geometry(entry: float, stop: float, direction: str,
                   config: Mapping[str, Any] | None) -> tuple[bool, float | None]:
    if config is None or direction not in ("LONG", "SHORT") or not all(
        math.isfinite(x) and x > 0 for x in (entry, stop)
    ):
        return False, None
    risk = entry-stop if direction == "LONG" else stop-entry
    if risk <= 0:
        return False, None
    target = entry + 3.0*risk if direction == "LONG" else entry - 3.0*risk
    if target <= 0:
        return False, None
    cost_fraction = 2.0*(float(config["fee_fraction_per_side"])+float(config["slippage_fraction_per_side"]))
    cost = entry*cost_fraction
    net_reward = abs(target-entry)-cost
    net_risk = risk+cost
    if net_reward <= 0 or net_risk <= 0:
        return False, None
    net_rr = net_reward/net_risk
    return net_rr >= MIN_NET_RR_RESEARCH, net_rr


def _true_ranges(rows: Sequence[Mapping[str, Any]]) -> list[float]:
    result = []
    previous = None
    for row in rows:
        high, low, close = _num(row, "high"), _num(row, "low"), _num(row, "close")
        tr = high - low if previous is None else max(high-low, abs(high-previous), abs(low-previous))
        result.append(tr)
        previous = close
    return result


def _bb_width(closes: Sequence[float], window: int = 20) -> float:
    values = closes[-window:]
    if len(values) < window:
        raise ValueError("INSUFFICIENT_BB_WINDOW")
    mean = sum(values) / window
    variance = sum((x-mean)**2 for x in values) / window
    if mean <= 0:
        raise ValueError("INVALID_BB_MEAN")
    return 4.0 * math.sqrt(variance) / mean


def _base_rows(rows: Any, observed_at: datetime) -> tuple[list[dict[str, Any]], str, datetime]:
    if not isinstance(rows, list) or len(rows) < 80:
        raise ValueError("INSUFFICIENT_CLOSED_15M_HISTORY")
    eligible = []
    previous_open = None
    for row in rows:
        if not isinstance(row, dict) or row.get("schema") != "hes_global_candle_v1" or row.get("source") != SOURCE or row.get("symbol") != SYMBOL or row.get("timeframe") != TIMEFRAME or row.get("closed") is not True:
            raise ValueError("NON_CANONICAL_OR_OPEN_CANDLE")
        close_time = row.get("close_time")
        open_time = row.get("open_time")
        if type(close_time) is not int or type(open_time) is not int:
            raise ValueError("INVALID_15M_CANDLE_TIME_TYPE")
        if close_time != open_time + 900:
            raise ValueError("INVALID_15M_CANDLE_INTERVAL")
        if close_time * 1000 > int(observed_at.timestamp()*1000):
            continue
        if previous_open is not None and open_time - previous_open != 900:
            raise ValueError("CLOSED_15M_CANDLE_GAP_OR_OVERLAP")
        previous_open = open_time
        eligible.append(row)
    if len(eligible) < 80:
        raise ValueError("INSUFFICIENT_ASOF_CLOSED_CANDLES")
    # `observed_at` is the market-data observation time, not the candle close
    # boundary. Keep the two timestamps distinct and bind the assessment to
    # the latest fully closed 15m candle at or before that observation.
    setup_close = datetime.fromtimestamp(eligible[-1]["close_time"], timezone.utc)
    window = eligible[-240:]
    return window, _sha(window), setup_close


def _features_breakout(rows: Sequence[Mapping[str, Any]], regime: str, cost_config: Mapping[str, Any] | None) -> tuple[dict[str, bool], str | None, float | None]:
    prior = rows[-22:-2]
    breakout = rows[-2]
    retest = rows[-1]
    prior_high = max(_num(r, "high") for r in prior)
    prior_low = min(_num(r, "low") for r in prior)
    atrs = _true_ranges(rows[-16:])
    atr = sum(atrs[-14:]) / 14
    if atr <= 0:
        raise ValueError("ATR_INVALID")
    close_b = _num(breakout, "close")
    low_r, high_r, close_r = _num(retest, "low"), _num(retest, "high"), _num(retest, "close")
    long_break = close_b > prior_high
    short_break = close_b < prior_low
    long_retest = long_break and low_r <= prior_high + 0.25*atr and close_r > prior_high
    short_retest = short_break and high_r >= prior_low - 0.25*atr and close_r < prior_low
    side = "LONG" if long_retest else "SHORT" if short_retest else None
    mfi = _mfi(rows[-15:])
    flow = (side == "LONG" and mfi >= 50) or (side == "SHORT" and mfi <= 50)
    stop = low_r-0.1*atr if side == "LONG" else high_r+0.1*atr if side == "SHORT" else 0.0
    geometry_ok, net_rr = _cost_geometry(close_r, stop, side, cost_config) if side else (False, None)
    return {
        "breakout_closed": bool(long_break or short_break),
        "acceptance_outside_boundary": bool((long_break and close_r > prior_high) or (short_break and close_r < prior_low)),
        "retest_confirmed": bool(long_retest or short_retest),
        "breakout_directional_flow": bool(flow),
        "breakout_regime_direction_alignment": bool(side and (
            regime == "RANGE" or (regime == "UPTREND" and side == "LONG")
            or (regime == "DOWNTREND" and side == "SHORT")
        )),
        "breakout_invalidation_defined": bool(side and stop > 0 and ((side == "LONG" and stop < close_r) or (side == "SHORT" and stop > close_r))),
        "breakout_cost_adjusted_geometry": geometry_ok,
    }, side, net_rr


def _mfi(rows: Sequence[Mapping[str, Any]]) -> float:
    positive = negative = 0.0
    previous = None
    for row in rows:
        typical = (_num(row,"high")+_num(row,"low")+_num(row,"close"))/3
        flow = typical * _num(row,"volume")
        if previous is not None:
            if typical > previous: positive += flow
            elif typical < previous: negative += flow
        previous = typical
    if negative == 0:
        return 100.0 if positive > 0 else 50.0
    return 100.0 - 100.0/(1.0 + positive/negative)


def _features_volatility(rows: Sequence[Mapping[str, Any]], structure: Mapping[str, Any], regime: str, cost_config: Mapping[str, Any] | None) -> tuple[dict[str, bool], str | None, float | None]:
    closes = [_num(r, "close") for r in rows]
    tr = _true_ranges(rows)
    atr_now = sum(tr[-14:])/14
    prior_atr = [sum(tr[i-14:i])/14 for i in range(max(14,len(tr)-40),len(tr)-14)]
    widths = [_bb_width(closes[:i]) for i in range(20,len(closes)+1)]
    prior_widths = widths[-21:-1]
    width_now = widths[-1]
    compression_window = widths[-41:-21]
    baseline_window = widths[-61:-41]
    compressed = bool(len(compression_window) == 20 and len(baseline_window) == 20 and median(compression_window) <= median(baseline_window) * 0.75)
    expanded = bool(prior_atr and len(compression_window) == 20 and atr_now >= median(prior_atr)*1.25 and width_now >= median(compression_window)*1.25)
    events = structure.get("events", []) if isinstance(structure, Mapping) else []
    directional_events = [x for x in events if x in ("BOS_BULLISH","CHOCH_BULLISH","BOS_BEARISH","CHOCH_BEARISH")]
    latest_event = directional_events[-1] if directional_events else None
    direction = "LONG" if latest_event in ("BOS_BULLISH","CHOCH_BULLISH") else "SHORT" if latest_event in ("BOS_BEARISH","CHOCH_BEARISH") else None
    mfi = _mfi(rows[-15:])
    flow = (direction == "LONG" and mfi >= 50) or (direction == "SHORT" and mfi <= 50)
    atr_now = sum(tr[-14:])/14
    current = rows[-1]
    stop = _num(current,"low")-0.1*atr_now if direction == "LONG" else _num(current,"high")+0.1*atr_now if direction == "SHORT" else 0.0
    entry = _num(current,"close")
    geometry_ok, net_rr = _cost_geometry(entry, stop, direction, cost_config) if direction else (False, None)
    return {
        "compression_preceded": compressed,
        "volatility_expansion_confirmed": expanded,
        "directional_displacement": bool(direction),
        "structure_confirmation": bool(direction and structure.get("status") == "OBSERVED"),
        "volatility_directional_flow": bool(flow),
        "volatility_regime_direction_alignment": bool(direction and (
            regime == "RANGE" or (regime == "UPTREND" and direction == "LONG")
            or (regime == "DOWNTREND" and direction == "SHORT")
        )),
        "volatility_invalidation_defined": bool(direction and stop > 0 and ((direction == "LONG" and stop < entry) or (direction == "SHORT" and stop > entry))),
        "volatility_cost_adjusted_geometry": geometry_ok,
    }, direction, net_rr


def _seal_assessment(payload: dict[str, Any]) -> dict[str, Any]:
    payload["assessment_sha256"] = _sha(payload)
    return payload


def assess_strategy_families(
    *, source: str, symbol: str, timeframe: str, regime: str,
    observed_at: Any, now: Any, rows_15m: Any, structure: Mapping[str, Any],
    trend_candidate: Any, range_evidence: Any,
    trend_evidence_bundle: Any = None, trend_quality: Any = None,
) -> dict[str, Any]:
    """Assess all four families independently, returning research eligibility only."""
    if source != SOURCE or symbol != SYMBOL or timeframe != TIMEFRAME:
        return _seal_assessment({"schema":SCHEMA,"version":VERSION,"status":"BLOCKED","source":source,"symbol":symbol,"setup_timeframe":timeframe,"observed_at":None,"reason_codes":["NON_CANONICAL_SCOPE"],"families":{},"research_eligible_family_ids":[],"candidate_generation_authorized":False,"confirmation_approved":False,"risk_approved":False,"execution_enabled":False,"orders_placed":False})
    try:
        observed, current = _aware(observed_at), _aware(now)
        age=(current-observed).total_seconds()
        if age < 0 or age > MAX_AGE_SECONDS:
            raise ValueError("SETUP_CONTEXT_STALE_OR_FUTURE")
        rows, candle_hash, setup_close = _base_rows(rows_15m, observed)
        setup_age = (current - setup_close).total_seconds()
        if setup_age < 0 or setup_age > MAX_AGE_SECONDS:
            raise ValueError("SETUP_CANDLE_STALE_OR_FUTURE")
        cost_config, cost_hash = _load_cost_context()
        breakout, breakout_side, breakout_net_rr = _features_breakout(rows, regime, cost_config)
        volatility, volatility_side, volatility_net_rr = _features_volatility(rows, structure, regime, cost_config)
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        return _seal_assessment({"schema":SCHEMA,"version":VERSION,"status":"BLOCKED","source":source,"symbol":symbol,"setup_timeframe":timeframe,"observed_at":observed.isoformat() if "observed" in locals() else None,"reason_codes":[str(exc)[:160]],"families":{},"research_eligible_family_ids":[],"candidate_generation_authorized":False,"confirmation_approved":False,"risk_approved":False,"execution_enabled":False,"orders_placed":False})
    stamp=setup_close.isoformat()
    market_observed_stamp=observed.isoformat()
    trend_state=getattr(trend_candidate,"state",None)
    trend_side="LONG" if trend_state=="CANDIDATE_LONG" else "SHORT" if trend_state=="CANDIDATE_SHORT" else None
    trend_check_states={getattr(check,"name",""):getattr(check,"state","UNKNOWN")
                        for check in getattr(trend_evidence_bundle,"strategy_checks",())}
    trend_quality_pass=getattr(trend_quality,"state",None)=="PASS"
    trend_provider_direction=getattr(trend_evidence_bundle,"direction","UNKNOWN")
    provider_side="LONG" if trend_provider_direction=="BULLISH" else "SHORT" if trend_provider_direction=="BEARISH" else None
    geometry=getattr(trend_evidence_bundle,"risk_geometry",None)
    trend_net_rr=None
    trend_cost_geometry=False
    if geometry and cost_config is not None:
        entry,stop,target=(float(x) for x in geometry)
        trend_cost_geometry,trend_net_rr=_cost_geometry(entry,stop,provider_side,cost_config)
    latest_directional=next((x for x in reversed(structure.get("events",[]))
        if x in ("BOS_BULLISH","CHOCH_BULLISH","BOS_BEARISH","CHOCH_BEARISH")),None)
    range_candidate=getattr(range_evidence,"candidate",None)
    range_check_states={getattr(check,"name",""):getattr(check,"state","UNKNOWN")
                        for check in getattr(range_evidence,"checks",())}
    range_feats={
        "range_candidate_valid":range_check_states.get("candidate_valid")=="PASS",
        "range_persistence":range_check_states.get("range_persistence")=="PASS",
        "range_boundary_location":range_check_states.get("range_boundary_location")=="PASS",
        "range_reversal_trigger":range_check_states.get("reversal_trigger")=="PASS",
        "range_direction_regime_alignment":range_check_states.get("direction_regime_alignment")=="PASS",
        "range_directional_flow_confirmation":range_check_states.get("directional_flow_confirmation")=="PASS",
        "range_structure_confirmation":range_check_states.get("structure_confirmation")=="PASS",
        "range_cost_adjusted_geometry":range_check_states.get("cost_adjusted_geometry")=="PASS",
        "range_direction_present":bool(isinstance(range_candidate,Mapping) and range_candidate.get("direction") in ("LONG","SHORT")),
        "range_cost_context_bound":bool(isinstance(range_candidate,Mapping) and range_candidate.get("cost_model_sha256")),
    }
    trend_feats={
        "trend_candidate_present":bool(trend_side),
        "trend_regime_aligned":bool((regime=="UPTREND" and trend_side=="LONG") or (regime=="DOWNTREND" and trend_side=="SHORT")),
        "trend_structure_confirmed":bool((trend_side=="LONG" and latest_directional in ("BOS_BULLISH","CHOCH_BULLISH")) or (trend_side=="SHORT" and latest_directional in ("BOS_BEARISH","CHOCH_BEARISH"))),
        "htf_trend_alignment":trend_check_states.get("htf_trend_alignment")=="PASS",
        "pullback_location":trend_check_states.get("pullback_location")=="PASS",
        "reversal_break_confirmation":trend_check_states.get("reversal_break_confirmation")=="PASS",
        "mfi_confirmation":trend_check_states.get("mfi_confirmation")=="PASS",
        "adx_directional_strength":trend_check_states.get("adx_directional_strength")=="PASS",
        "risk_geometry_3_to_1":trend_check_states.get("risk_geometry_3_to_1")=="PASS",
        "strategy_quality_pass":trend_quality_pass and provider_side==trend_side,
        "cost_adjusted_geometry":trend_cost_geometry,
    }
    feature_maps={
        "trend_continuation":trend_feats,
        "breakout_retest":breakout,
        "range_reversion":range_feats,
        "volatility_expansion":volatility,
    }
    dispatch_features={}
    for family_id, feature_values in feature_maps.items():
        for feature_name, feature_value in feature_values.items():
            if feature_name in dispatch_features:
                raise ValueError("DUPLICATE_FAMILY_FEATURE_CONTRACT:"+feature_name)
            dispatch_features[feature_name]={
                "value":feature_value,
                "evidence_ref":f"gateio://{SYMBOL}/{TIMEFRAME}/{candle_hash}/{family_id}/{feature_name}",
                "observed_at":stamp,
                "source_sha256":candle_hash,
            }
    dispatch_result=dispatch_research_families(
        source=source,symbol=symbol,timeframe=timeframe,regime=regime,
        closed_candle=True,observed_at=stamp,now=current,
        candle_window_sha256=candle_hash,feature_evidence=dispatch_features,
    )
    if dispatch_result.get("status")=="BLOCKED":
        return _seal_assessment({
            "schema":SCHEMA,"version":VERSION,"status":"BLOCKED",
            "source":source,"symbol":symbol,"setup_timeframe":timeframe,
            "observed_at":stamp,"reason_codes":list(dispatch_result.get("reason_codes",[])),
            "families":{},"research_eligible_family_ids":[],
            "research_dispatch_status":"BLOCKED",
            "candidate_generation_authorized":False,"confirmation_approved":False,
            "risk_approved":False,"execution_enabled":False,"orders_placed":False,
        })
    eligible_ids={item["family_id"] for item in dispatch_result.get("research_eligible_families",[])}
    family_rejections=dispatch_result.get("family_rejections",{})

    def pack(fid, feats, side, diagnostics=None):
        profile=FAMILIES[fid]
        required=list(profile["features"])
        ready=fid in eligible_ids
        reasons=[] if ready else list(family_rejections.get(fid,["NOT_RESEARCH_ELIGIBLE"]))
        family_version=profile["version"]
        digest=_sha({
            "candle_window_sha256":candle_hash,"family_id":fid,"family_version":family_version,
            "status":"RESEARCH_ELIGIBLE" if ready else "NOT_ELIGIBLE",
            "direction":side,"features":feats,"required_features":required,
            "diagnostics":diagnostics or {},"reason_codes":reasons,"observed_at":stamp,
        })
        return {
            "family_id":fid,"family_version":family_version,
            "status":"RESEARCH_ELIGIBLE" if ready else "NOT_ELIGIBLE",
            "direction":side,"features":feats,"required_features":required,
            "diagnostics":diagnostics or {},"reason_codes":reasons,
            "evidence_sha256":digest,"candle_window_sha256":candle_hash,
            "observed_at":stamp,"candidate_generation_authorized":False,
            "confirmation_approved":False,"risk_approved":False,
            "execution_enabled":False,"orders_placed":False,
        }

    families = {
        "trend_continuation":pack("trend_continuation",trend_feats,trend_side,diagnostics={"strategy_provider_direction":trend_provider_direction,"strategy_quality_status":getattr(trend_quality,"state","UNKNOWN"),"net_rr_estimate":trend_net_rr,"cost_model_status":"ASSUMPTION_BASED" if cost_config else "UNAVAILABLE","cost_model_sha256":cost_hash}),
        "breakout_retest":pack("breakout_retest",breakout,breakout_side,diagnostics={"net_rr_estimate":breakout_net_rr,"cost_model_status":"ASSUMPTION_BASED" if cost_config else "UNAVAILABLE","cost_model_sha256":cost_hash}),
        "range_reversion":pack("range_reversion",range_feats,range_candidate.get("direction") if isinstance(range_candidate,Mapping) else None,diagnostics={"net_rr_estimate":range_candidate.get("net_rr_estimate") if isinstance(range_candidate,Mapping) else None,"cost_model_status":getattr(range_evidence,"cost_model_status","UNAVAILABLE"),"cost_model_sha256":getattr(range_evidence,"cost_model_sha256",None)}),
        "volatility_expansion":pack("volatility_expansion",volatility,volatility_side,diagnostics={"net_rr_estimate":volatility_net_rr,"cost_model_status":"ASSUMPTION_BASED" if cost_config else "UNAVAILABLE","cost_model_sha256":cost_hash}),
    }
    return _seal_assessment({
        "schema":SCHEMA,"version":VERSION,"source":SOURCE,"symbol":SYMBOL,
        "setup_timeframe":TIMEFRAME,"observed_at":stamp,"market_observed_at":market_observed_stamp,"regime":regime,
        "status":"ASSESSED","candle_window_sha256":candle_hash,"families":families,
        "research_dispatch_status":dispatch_result.get("status"),
        "research_dispatch_version":dispatch_result.get("version"),
        "research_eligible_family_ids":[fid for fid,item in families.items() if item["status"]=="RESEARCH_ELIGIBLE"],
        "candidate_generation_authorized":False,"confirmation_approved":False,
        "risk_approved":False,"execution_enabled":False,"orders_placed":False,
    })