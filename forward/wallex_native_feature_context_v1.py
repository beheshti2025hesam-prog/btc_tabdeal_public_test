"""Fail-closed research feature context for verified native Wallex candles.

This contract is intentionally separate from the legacy BTC_USDT/15m sequence
consumer. It computes descriptive candle context only: no signals, trade
decisions, execution, historical outcomes, or sequence inference.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any

TIMEFRAME_BY_RESOLUTION = {"1": ("1m", 60), "60": ("1h", 3600), "1D": ("1D", 86400)}
MAX_CANDLES = 10_000


class WallexFeatureContextError(ValueError):
    """Observation record is unsafe or incompatible with this consumer contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _aware(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise WallexFeatureContextError(f"{field} must be an ISO timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise WallexFeatureContextError(f"{field} is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WallexFeatureContextError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise WallexFeatureContextError(f"{field} must be a decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise WallexFeatureContextError(f"{field} must be a decimal") from None
    if not result.is_finite():
        raise WallexFeatureContextError(f"{field} must be finite")
    return result


def build_wallex_feature_context_v1(
    record: dict[str, Any], *, as_of: datetime, expected_symbol: str = "BTCUSDT"
) -> dict[str, Any]:
    """Validate a hash-locked observation and derive descriptive context only."""
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise WallexFeatureContextError("as_of must be timezone-aware")
    as_of = as_of.astimezone(timezone.utc)
    if not isinstance(record, dict):
        raise WallexFeatureContextError("observation record must be an object")
    if record.get("schema") != "HES_WALLEX_CANDLE_OBSERVATION_V1":
        raise WallexFeatureContextError("unsupported observation schema")
    if record.get("status") != "OBSERVED" or record.get("reason") != "OK":
        raise WallexFeatureContextError("only complete, fresh OBSERVED records are accepted")
    if record.get("venue") != "wallex":
        raise WallexFeatureContextError("unsupported venue")
    if record.get("symbol") != expected_symbol or expected_symbol != "BTCUSDT":
        raise WallexFeatureContextError("unsupported symbol scope")
    resolution = record.get("resolution")
    if resolution not in TIMEFRAME_BY_RESOLUTION:
        raise WallexFeatureContextError("unsupported native resolution")
    timeframe, step = TIMEFRAME_BY_RESOLUTION[resolution]
    if record.get("timeframe") != timeframe:
        raise WallexFeatureContextError("resolution/timeframe mismatch")
    max_age = record.get("max_age_seconds")
    if type(max_age) is not int or max_age < 0:
        raise WallexFeatureContextError("invalid freshness policy")
    observed_at = _aware(record.get("observed_at"), "observed_at")
    if observed_at > as_of:
        raise WallexFeatureContextError("record is from the future")
    if record.get("gaps") != []:
        raise WallexFeatureContextError("gap metadata is missing or non-empty")
    provenance = record.get("source_provenance")
    if not isinstance(provenance, dict):
        raise WallexFeatureContextError("source provenance is required")
    if provenance.get("raw_response_bytes_retained") is not False:
        raise WallexFeatureContextError("unexpected raw-source provenance claim")
    if provenance.get("raw_response_sha256") is not None:
        raise WallexFeatureContextError("raw-response hash claim is unsupported by this observation schema")

    claimed_record_hash = record.get("record_sha256")
    if not isinstance(claimed_record_hash, str) or len(claimed_record_hash) != 64:
        raise WallexFeatureContextError("record hash is missing")
    record_body = {key: value for key, value in record.items() if key != "record_sha256"}
    if _sha256(_canonical(record_body).encode("utf-8")) != claimed_record_hash:
        raise WallexFeatureContextError("observation record hash mismatch")

    candles = record.get("candles")
    if not isinstance(candles, list) or len(candles) < 2:
        raise WallexFeatureContextError("at least two closed candles are required")
    if len(candles) > MAX_CANDLES:
        raise WallexFeatureContextError("candle count exceeds contract bound")

    parsed: list[dict[str, Any]] = []
    previous_open: datetime | None = None
    previous_close: datetime | None = None
    for index, candle in enumerate(candles):
        if not isinstance(candle, dict):
            raise WallexFeatureContextError(f"candles[{index}] must be an object")
        if (candle.get("venue") != "wallex" or candle.get("symbol") != expected_symbol
                or candle.get("resolution") != resolution or candle.get("timeframe") != timeframe):
            raise WallexFeatureContextError(f"candles[{index}] scope mismatch")
        open_time = _aware(candle.get("open_time"), f"candles[{index}].open_time")
        close_time = _aware(candle.get("close_time"), f"candles[{index}].close_time")
        source_observed = _aware(candle.get("source_observed_at"), f"candles[{index}].source_observed_at")
        source_ts = candle.get("source_timestamp")
        if type(source_ts) is not int or source_ts != int(open_time.timestamp()):
            raise WallexFeatureContextError(f"candles[{index}] source timestamp mismatch")
        if close_time.timestamp() - open_time.timestamp() != step:
            raise WallexFeatureContextError(f"candles[{index}] interval length mismatch")
        if close_time > as_of or source_observed < close_time or source_observed > as_of:
            raise WallexFeatureContextError(f"candles[{index}] is not causally closed/observed")
        if (previous_open is not None and
                (open_time <= previous_open or previous_close != open_time)):
            raise WallexFeatureContextError("candles are unordered or contain missing intervals")

        values = {key: _decimal(candle.get(key), f"candles[{index}].{key}")
                  for key in ("open", "high", "low", "close", "volume")}
        op, high, low, close, volume = (values[k] for k in ("open", "high", "low", "close", "volume"))
        if min(op, high, low, close) <= 0 or volume < 0:
            raise WallexFeatureContextError(f"candles[{index}] has invalid OHLCV values")
        if low > min(op, close) or high < max(op, close) or low > high:
            raise WallexFeatureContextError(f"candles[{index}] violates OHLC bounds")

        candle_body = {key: value for key, value in candle.items() if key != "canonical_candle_sha256"}
        fingerprint = candle.get("canonical_candle_sha256")
        if not isinstance(fingerprint, str) or _sha256(_canonical(candle_body).encode("utf-8")) != fingerprint:
            raise WallexFeatureContextError(f"candles[{index}] canonical hash mismatch")

        if as_of.timestamp() - source_observed.timestamp() > max_age:
            raise WallexFeatureContextError("source observation is stale")

        parsed.append({**values, "open_time": open_time, "close_time": close_time})
        previous_open, previous_close = open_time, close_time

    latest = parsed[-1]
    prior = parsed[-2]
    if as_of.timestamp() - latest["close_time"].timestamp() > max_age:
        raise WallexFeatureContextError("latest candle is stale")

    close_change = (latest["close"] / prior["close"] - Decimal("1")) * Decimal("100")
    range_pct = (latest["high"] - latest["low"]) / latest["close"] * Decimal("100")
    volume_sum = sum((item["volume"] for item in parsed), Decimal("0"))
    higher_close = latest["close"] > prior["close"]
    higher_high = latest["high"] > prior["high"]
    lower_close = latest["close"] < prior["close"]
    lower_low = latest["low"] < prior["low"]
    if higher_close and higher_high:
        context = "UP_CONTEXT"
    elif lower_close and lower_low:
        context = "DOWN_CONTEXT"
    else:
        context = "MIXED_CONTEXT"

    return {
        "schema": "HES_WALLEX_NATIVE_FEATURE_CONTEXT_V1",
        "status": "FEATURE_CONTEXT_OBSERVED_RESEARCH_ONLY",
        "observed_at": as_of.isoformat(),
        "venue": "wallex",
        "symbol": expected_symbol,
        "resolution": resolution,
        "timeframe": timeframe,
        "input_record_sha256": claimed_record_hash,
        "input_candle_count": len(parsed),
        "latest_candle_close_time": latest["close_time"].isoformat(),
        "features": {
            "last_close": str(latest["close"]),
            "close_change_pct_last_two": str(close_change),
            "latest_range_pct_of_close": str(range_pct),
            "volume_sum_observed_window": str(volume_sum),
            "directional_context_last_two": context,
        },
        "sequence_semantics": "NOT_APPLICABLE_NATIVE_OHLCV",
        "raw_source_replay_verified": False,
        "historical_inputs_used": False,
        "signal_generated": False,
        "trade_decision_generated": False,
        "execution_enabled": False,
    }
