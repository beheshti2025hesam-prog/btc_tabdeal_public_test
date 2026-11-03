"""Advisory-only 1m entry-timing evaluator for HES Trade Agent.

The 15m Strategy Policy V2 setup remains authoritative. The 1m layer can only
return READY/WAIT/BLOCKED after a provenance-bound 15m context and an approved
Risk Gate. It never changes direction, bypasses risk, or executes orders.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping
import math
import re


CONTEXT_SCHEMA = "hes_strategy_entry_context_v1"
CANDLE_SCHEMA = "hes_global_candle_v1"
MARKET_SOURCE = "gateio_public_spot"
MARKET_SYMBOL = "BTC_USDT"
MINIMUM_RR = 3.0
MAX_CANDLE_AGE_SECONDS = 120


@dataclass(frozen=True)
class PrecisionEntryResult:
    schema: str
    state: str
    direction: str
    reason_codes: tuple[str, ...]
    evidence: dict[str, Any]
    authority: str = "ADVISORY_ONLY_RISK_GATE_UNCHANGED"
    execution_enabled: bool = False
    orders_placed: bool = False


def _ema(values: list[float], period: int) -> float:
    alpha = 2.0 / (period + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _blocked(direction: str, code: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return asdict(PrecisionEntryResult(
        "hes_precision_entry_v1", "BLOCKED", direction, (code,), evidence or {}
    ))


def _valid_context(
    context: Mapping[str, Any], *, direction: str, now_s: int, min_rr: float
) -> tuple[dict[str, float] | None, str | None]:
    if context.get("schema") != CONTEXT_SCHEMA:
        return None, "ENTRY_CONTEXT_SCHEMA_INVALID"
    if context.get("source") != "strategy_policy_v2":
        return None, "ENTRY_CONTEXT_SOURCE_INVALID"
    if context.get("symbol") != MARKET_SYMBOL or context.get("timeframe") != "15m":
        return None, "ENTRY_CONTEXT_SCOPE_INVALID"
    if context.get("direction") != direction:
        return None, "ENTRY_CONTEXT_DIRECTION_MISMATCH"
    setup_id = context.get("setup_id")
    digest = context.get("evidence_sha256")
    if not isinstance(setup_id, str) or not setup_id.strip() or len(setup_id) > 256:
        return None, "ENTRY_CONTEXT_ID_INVALID"
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        return None, "ENTRY_CONTEXT_PROVENANCE_INVALID"
    valid_until = context.get("valid_until")
    if type(valid_until) is not int or valid_until < now_s:
        return None, "ENTRY_CONTEXT_EXPIRED"
    values: dict[str, float] = {}
    for key in ("entry_zone_low", "entry_zone_high", "stop_price", "target_price"):
        raw = context.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None, "ENTRY_CONTEXT_INVALID"
        value = float(raw)
        if not math.isfinite(value) or value <= 0:
            return None, "ENTRY_CONTEXT_INVALID"
        values[key] = value
    low, high = values["entry_zone_low"], values["entry_zone_high"]
    stop, target = values["stop_price"], values["target_price"]
    if low > high:
        return None, "ENTRY_CONTEXT_INVALID"
    if direction == "LONG":
        if not stop < low <= high < target:
            return None, "STOP_TARGET_DIRECTION_INVALID"
        worst_entry = high
        risk, reward = worst_entry - stop, target - worst_entry
    else:
        if not target < low <= high < stop:
            return None, "STOP_TARGET_DIRECTION_INVALID"
        worst_entry = low
        risk, reward = stop - worst_entry, worst_entry - target
    rr = reward / risk if risk > 0 else 0.0
    values["worst_case_rr"] = rr
    if not math.isfinite(rr) or rr < min_rr:
        return None, "RISK_REWARD_BELOW_MINIMUM"
    return values, None


def evaluate_precision_entry(
    *,
    setup_direction: str,
    candles_1m: list[dict[str, Any]],
    setup_validated_15m: bool,
    risk_gate_state: str,
    now_s: int,
    setup_context: dict[str, Any] | None = None,
    min_rr: float = MINIMUM_RR,
    max_age_s: int = MAX_CANDLE_AGE_SECONDS,
) -> dict[str, Any]:
    """Evaluate a 1m trigger from validated closed Gate.io candles.

    setup_context is accepted only from the verified Strategy Policy V2 15m
    evidence chain. It must carry a stable setup ID, evidence digest, expiry,
    direction, and explicit entry/stop/target geometry. The engine does not
    infer or invent an entry zone from 1m data.
    """
    direction = str(setup_direction).upper()
    evidence: dict[str, Any] = {"bars": len(candles_1m) if isinstance(candles_1m, list) else 0}

    # Report upstream authority failures before validating downstream direction.
    # A missing 15m setup is the primary reason a NONE direction is expected.
    if setup_validated_15m is not True:
        return _blocked(direction, "15M_SETUP_NOT_VALIDATED", evidence)
    if risk_gate_state != "RISK_APPROVED":
        return _blocked(direction, "RISK_GATE_NOT_APPROVED", evidence)
    if direction not in {"LONG", "SHORT"}:
        return _blocked(direction, "SETUP_DIRECTION_INVALID", evidence)
    if isinstance(now_s, bool) or not isinstance(now_s, int) or now_s <= 0:
        return _blocked(direction, "OBSERVATION_TIME_INVALID", evidence)
    if isinstance(min_rr, bool) or not isinstance(min_rr, (int, float)) or not math.isfinite(min_rr) or min_rr < MINIMUM_RR:
        return _blocked(direction, "MINIMUM_RR_POLICY_INVALID", evidence)
    if type(max_age_s) is not int or not 1 <= max_age_s <= MAX_CANDLE_AGE_SECONDS:
        return _blocked(direction, "MAX_CANDLE_AGE_POLICY_INVALID", evidence)
    if not isinstance(candles_1m, list) or len(candles_1m) < 50:
        return _blocked(direction, "INSUFFICIENT_1M_CANDLES", evidence)
    if not isinstance(setup_context, dict):
        return _blocked(direction, "ENTRY_CONTEXT_MISSING", evidence)

    context, context_error = _valid_context(
        setup_context, direction=direction, now_s=now_s, min_rr=float(min_rr)
    )
    if context_error:
        return _blocked(direction, context_error, evidence)
    assert context is not None

    try:
        rows = candles_1m[-50:]
        values: list[tuple[float, float, float, float, float]] = []
        timestamps: list[int] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("CANDLE_SCHEMA_INVALID")
            if (
                row.get("schema") != CANDLE_SCHEMA
                or row.get("source") != MARKET_SOURCE
                or row.get("symbol") != MARKET_SYMBOL
                or row.get("timeframe") != "1m"
            ):
                raise ValueError("SOURCE_IDENTITY_MISMATCH")
            ts, close_time = row.get("open_time"), row.get("close_time")
            if type(ts) is not int or type(close_time) is not int or ts < 0 or ts % 60:
                raise ValueError("CANDLE_SCHEMA_INVALID")
            if row.get("closed") is not True or close_time != ts + 60:
                raise ValueError("OPEN_CANDLE_REJECTED" if row.get("closed") is not True else "CANDLE_SCHEMA_INVALID")
            numeric = []
            for key in ("open", "high", "low", "close", "volume", "quote_volume"):
                raw = row.get(key)
                if isinstance(raw, bool):
                    raise ValueError("CANDLE_SCHEMA_INVALID")
                try:
                    value = float(raw)
                except (TypeError, ValueError, OverflowError):
                    raise ValueError("CANDLE_SCHEMA_INVALID")
                if not math.isfinite(value):
                    raise ValueError("CANDLE_NON_FINITE_VALUE")
                numeric.append(value)
            o, h, l, c, volume, quote_volume = numeric
            if min(o, h, l, c) <= 0 or volume < 0 or quote_volume < 0 or h < max(o, c, l) or l > min(o, c, h):
                raise ValueError("CANDLE_OHLC_INVALID")
            timestamps.append(ts)
            values.append((o, h, l, c, volume))
        if any(right - left != 60 for left, right in zip(timestamps, timestamps[1:])):
            raise ValueError("CANDLE_INTERVAL_GAP")
        age = now_s - rows[-1]["close_time"]
        if age < 0 or age > max_age_s:
            raise ValueError("CANDLE_FEED_STALE")
    except (KeyError, TypeError, ValueError) as exc:
        allowed = {
            "SOURCE_IDENTITY_MISMATCH", "CANDLE_SCHEMA_INVALID", "CANDLE_NON_FINITE_VALUE",
            "CANDLE_OHLC_INVALID", "OPEN_CANDLE_REJECTED", "CANDLE_INTERVAL_GAP", "CANDLE_FEED_STALE",
        }
        code = str(exc) if str(exc) in allowed else "CANDLE_SCHEMA_INVALID"
        return _blocked(direction, code, evidence)

    closes = [item[3] for item in values]
    typical = [(item[1] + item[2] + item[3]) / 3.0 for item in values]
    volumes = [item[4] for item in values]
    total_volume = sum(volumes)
    if total_volume <= 0:
        return _blocked(direction, "VOLUME_UNAVAILABLE", evidence)

    vwap = sum(price * volume for price, volume in zip(typical, volumes)) / total_volume
    ema50 = _ema(closes, 50)
    last = values[-1]
    prior = values[:-1]
    prior_high = max(item[1] for item in prior[-10:])
    prior_low = min(item[2] for item in prior[-10:])
    prior_lows = [item[2] for item in prior[-5:]]
    prior_highs = [item[1] for item in prior[-5:]]
    sweep_low = last[2] < min(prior_lows) and last[3] > min(prior_lows)
    sweep_high = last[1] > max(prior_highs) and last[3] < max(prior_highs)
    bullish_break = last[3] > prior_high
    bearish_break = last[3] < prior_low
    average_volume = sum(volumes[-21:-1]) / 20.0
    volume_ok = average_volume > 0 and last[4] >= average_volume

    zone_low = context["entry_zone_low"]
    zone_high = context["entry_zone_high"]
    stop = context["stop_price"]
    target = context["target_price"]
    planned_entry = (zone_low + zone_high) / 2.0
    worst_case_rr = context["worst_case_rr"]
    evidence.update({
        "setup_id": setup_context["setup_id"],
        "setup_evidence_sha256": setup_context["evidence_sha256"],
        "latest_close": last[3],
        "age_seconds": age,
        "liquidity_sweep_low": sweep_low,
        "liquidity_sweep_high": sweep_high,
        "bullish_micro_break": bullish_break,
        "bearish_micro_break": bearish_break,
        "volume_confirmation": volume_ok,
        "vwap_1m_50bar": vwap,
        "ema50_1m": ema50,
        "above_vwap": last[3] > vwap,
        "below_vwap": last[3] < vwap,
        "above_ema50": last[3] > ema50,
        "below_ema50": last[3] < ema50,
        "entry_zone_low": zone_low,
        "entry_zone_high": zone_high,
        "planned_entry": planned_entry,
        "stop_price": stop,
        "target_price": target,
        "planned_rr_worst_case": worst_case_rr,
        "minimum_rr": float(min_rr),
        "prior_micro_high": prior_high,
        "prior_micro_low": prior_low,
    })

    if not zone_low <= last[3] <= zone_high:
        return asdict(PrecisionEntryResult(
            "hes_precision_entry_v1", "WAIT", direction, ("PRICE_OUTSIDE_ENTRY_ZONE",), evidence
        ))

    if direction == "LONG":
        aligned = last[3] > vwap and last[3] > ema50
        structure_trigger = sweep_low or bullish_break
        candle_direction = last[3] > last[0]
    else:
        aligned = last[3] < vwap and last[3] < ema50
        structure_trigger = sweep_high or bearish_break
        candle_direction = last[3] < last[0]
    evidence["vwap_ema_alignment"] = aligned
    failed = []
    if not structure_trigger:
        failed.append("MICROSTRUCTURE_TRIGGER_NOT_CONFIRMED")
    if not volume_ok:
        failed.append("VOLUME_CONFIRMATION_MISSING")
    if not aligned:
        failed.append("VWAP_EMA_ALIGNMENT_MISSING")
    if not candle_direction:
        failed.append("ENTRY_CANDLE_DIRECTION_NOT_CONFIRMED")
    if failed:
        return asdict(PrecisionEntryResult(
            "hes_precision_entry_v1", "WAIT", direction, tuple(failed), evidence
        ))
    return asdict(PrecisionEntryResult(
        "hes_precision_entry_v1", "READY", direction, (), evidence
    ))
