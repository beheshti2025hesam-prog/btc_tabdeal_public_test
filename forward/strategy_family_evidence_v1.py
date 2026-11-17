"""Causal, Gate.io-only evidence adapter for the Range strategy family.

Consumes the exact persisted frames produced by global_market_data_reader_v1.
It performs no network I/O and emits research candidates only; confirmation,
Risk Gate approval, signal authorization and execution remain separate gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from core.data_engine.volatility import VolatilityCalculator
from core.feature_engine.ema import EMACalculator
from scripts.analyze_gateio_snapshot_v1 import rsi

from .confirmation_engine_v1 import ConfirmationCheck
from .native_ohlcv_gateio_v1 import from_persisted_global_rows
from .native_ohlcv_feature_adapter_v1 import to_feature_batch
from .range_opportunity_policy_v1 import RangeSnapshot, POLICY_VERSION, evaluate_range_candidate
from .strategy_evidence_provider_v1 import adx14, mfi14_series, _evidence_window_sha256
from .strategy_family_router_v1 import RANGE_MEAN_REVERSION_RESEARCH_V1

SCHEMA = "hes_strategy_family_evidence_v1"
VERSION = "hes-gateio-range-family-evidence-v1.0.0"
SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"
SETUP_TIMEFRAME = "15m"
REQUIRED_TIMEFRAMES = ("15m", "1h", "4h")
EVIDENCE_WINDOW_BARS = 240
MINIMUM_CANDLES_PER_TIMEFRAME = 200
RANGE_BOUNDARY_BARS = 36
RANGE_PERSISTENCE_BARS = 12
EMA_SLOPE_LOOKBACK = 3
OBSERVATION_INGESTION_TOLERANCE_MS = 60_000


@dataclass(frozen=True)
class StrategyFamilyEvidenceResultV1:
    family_id: str
    family_version: str
    status: str
    candidate: dict[str, Any] | None
    checks: tuple[ConfirmationCheck, ...]
    evidence_sha256: str | None
    features: dict[str, Any]
    blocked_reasons: tuple[str, ...]
    cost_model_status: str
    cost_model_sha256: str | None
    candidate_generation_authorized: bool = False
    confirmation_authority: bool = False
    risk_approved: bool = False
    execution_enabled: bool = False
    orders_placed: bool = False

    def as_dict(self) -> dict[str, Any]:
        candidate = dict(self.candidate) if self.candidate is not None else None
        if candidate is not None and isinstance(candidate.get("observed_at"), datetime):
            candidate["observed_at"] = candidate["observed_at"].astimezone(timezone.utc).isoformat()
        return {
            "schema": SCHEMA,
            "version": VERSION,
            "family_id": self.family_id,
            "family_version": self.family_version,
            "status": self.status,
            "candidate": candidate,
            "checks": [
                {"name": check.name, "state": check.state,
                 "evidence_ref": check.evidence_ref,
                 "observed_at": check.observed_at.astimezone(timezone.utc).isoformat()}
                for check in self.checks
            ],
            "evidence_sha256": self.evidence_sha256,
            "features": self.features,
            "blocked_reasons": list(self.blocked_reasons),
            "cost_model_status": self.cost_model_status,
            "cost_model_sha256": self.cost_model_sha256,
            "candidate_generation_authorized": False,
            "confirmation_authority": False,
            "risk_approved": False,
            "execution_enabled": False,
            "orders_placed": False,
        }


def _blocked(reason: str, *, features: dict[str, Any] | None = None,
             cost_model_status: str = "UNAVAILABLE", cost_model_sha256: str | None = None) -> StrategyFamilyEvidenceResultV1:
    return StrategyFamilyEvidenceResultV1(
        RANGE_MEAN_REVERSION_RESEARCH_V1.family_id,
        RANGE_MEAN_REVERSION_RESEARCH_V1.version,
        "BLOCKED", None, (), None, features or {}, (reason,),
        cost_model_status, cost_model_sha256,
    )


def _aware_utc(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("setup observation must be timezone-aware")
    return value.astimezone(timezone.utc)


def _load_simulation_cost_model() -> tuple[dict[str, Any], str]:
    path = Path(__file__).with_name("paper_risk_context_v1.json")
    raw = path.read_bytes()
    config = json.loads(raw.decode("utf-8"))
    scope = config.get("scope", {})
    safety = config.get("safety", {})
    if (
        config.get("status") != "SIMULATION_ONLY_NOT_LIVE_APPROVAL"
        or scope.get("source") != SOURCE
        or scope.get("symbol") != SYMBOL
        or scope.get("timeframe") != SETUP_TIMEFRAME
        or config.get("leverage") != 1
        or safety.get("live_execution_enabled") is not False
        or safety.get("orders_placed") is not False
    ):
        raise ValueError("SIMULATION_COST_MODEL_SCOPE_OR_SAFETY_INVALID")
    for key in ("fee_fraction_per_side", "slippage_fraction_per_side"):
        value = config.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("SIMULATION_COST_MODEL_VALUE_INVALID:" + key)
    return config, hashlib.sha256(raw).hexdigest()


def _atr14_sma(feature_candles) -> float | None:
    if len(feature_candles) < 15:
        return None
    snapshots = VolatilityCalculator().calculate(feature_candles[-15:])
    if not snapshots:
        return None
    value = snapshots[-1].average_true_range
    return value if math.isfinite(value) and value > 0 else None


def _ema50_slope_atr(feature_candles) -> float | None:
    atr = _atr14_sma(feature_candles)
    if atr is None:
        return None
    points = EMACalculator(50).calculate(feature_candles)
    if len(points) < EMA_SLOPE_LOOKBACK + 1:
        return None
    value = (points[-1].value - points[-1 - EMA_SLOPE_LOOKBACK].value) / atr
    return value if math.isfinite(value) else None


def _window_hashes(batches: Mapping[str, Any], *, as_of_ms: int) -> dict[str, str]:
    return {
        timeframe: _evidence_window_sha256(batch, as_of_ms=as_of_ms)
        for timeframe, batch in batches.items()
    }


def build_range_family_evidence(
    *, frames: Mapping[str, Any], source: str, symbol: str,
    observed_at: datetime, now_ms: int,
) -> StrategyFamilyEvidenceResultV1:
    """Build a source-bound Range sweep/reclaim candidate from closed Gate.io bars.

    Setup authority is 15m. 1h/4h are context only. The setup `as_of_ms` is
    the exclusive close boundary of the current 15m candle; every timeframe
    is filtered to candles whose inclusive native close millisecond is before
    that boundary. 1m is intentionally ignored.
    """
    if source != SOURCE or symbol != SYMBOL:
        return _blocked("CANONICAL_SOURCE_OR_SYMBOL_MISMATCH")
    try:
        obs = _aware_utc(observed_at)
    except ValueError as exc:
        return _blocked("SETUP_TIME_INVALID:" + str(exc))
    if type(now_ms) is not int or now_ms < 0:
        return _blocked("CURRENT_READ_TIME_INVALID")
    as_of_ms = int(obs.timestamp() * 1000)
    if as_of_ms > now_ms:
        return _blocked("SETUP_TIME_IN_FUTURE")
    if now_ms - as_of_ms > 15 * 60 * 1000 + OBSERVATION_INGESTION_TOLERANCE_MS:
        return _blocked("SETUP_15M_CANDLE_STALE")
    if not isinstance(frames, Mapping):
        return _blocked("MARKET_FRAMES_INVALID")

    batches: dict[str, Any] = {}
    feature_candles: dict[str, tuple] = {}
    native_eligible: dict[str, tuple] = {}
    try:
        for timeframe in REQUIRED_TIMEFRAMES:
            rows = frames.get(timeframe)
            if not isinstance(rows, list):
                return _blocked("MISSING_REQUIRED_TIMEFRAME:" + timeframe)
            # Filter to the 15m setup time BEFORE applying the bounded evidence
            # window. A later candle must not evict an older eligible row from
            # the hash or feature window during historical replay.
            eligible_rows = [
                row for row in rows
                if isinstance(row, Mapping)
                and type(row.get("close_time")) is int
                and row["close_time"] * 1000 <= as_of_ms
            ]
            if len(eligible_rows) < MINIMUM_CANDLES_PER_TIMEFRAME:
                return _blocked("INSUFFICIENT_CLOSED_CANDLES:" + timeframe)
            eligible_rows = eligible_rows[-EVIDENCE_WINDOW_BARS:]
            for row in eligible_rows:
                stamp = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    return _blocked("OBSERVATION_TIMESTAMP_NOT_AWARE:" + timeframe)
                if int(stamp.timestamp() * 1000) > as_of_ms + OBSERVATION_INGESTION_TOLERANCE_MS:
                    return _blocked("EVIDENCE_OBSERVED_AFTER_SETUP_WINDOW:" + timeframe)
            batch = from_persisted_global_rows(
                eligible_rows, timeframe=timeframe, now_ms=now_ms
            )
            if batch.gaps:
                return _blocked("SOURCE_GAP:" + timeframe)
            native = tuple(c for c in batch.candles if c.close_time_ms < as_of_ms)
            if len(native) < MINIMUM_CANDLES_PER_TIMEFRAME:
                return _blocked("INSUFFICIENT_ASOF_CANDLES:" + timeframe)
            feature_batch = to_feature_batch(
                batch, as_of_ms=as_of_ms, now_ms=now_ms
            )
            if feature_batch.gaps:
                return _blocked("FEATURE_SOURCE_GAP:" + timeframe)
            batches[timeframe] = batch
            native_eligible[timeframe] = native
            feature_candles[timeframe] = feature_batch.candles
    except (KeyError, TypeError, ValueError, OSError, OverflowError) as exc:
        return _blocked("SOURCE_DATA_INVALID:" + type(exc).__name__ + ":" + str(exc)[:120])

    native15 = native_eligible["15m"]
    if not native15 or native15[-1].close_time_ms + 1 != as_of_ms:
        return _blocked("SETUP_15M_CANDLE_CLOSE_MISMATCH")
    if len(native15) < RANGE_BOUNDARY_BARS + RANGE_PERSISTENCE_BARS + 1:
        return _blocked("INSUFFICIENT_RANGE_HISTORY")

    try:
        adx_by_tf = {tf: adx14(native_eligible[tf]) for tf in REQUIRED_TIMEFRAMES}
        if any(value is None for value in adx_by_tf.values()):
            return _blocked("ADX14_UNAVAILABLE")
        mfi_values = mfi14_series(native15)
        if len(mfi_values) < 2 or mfi_values[-1] is None or mfi_values[-2] is None:
            return _blocked("MFI14_UNAVAILABLE")
        close_values = [float(candle.close) for candle in native15]
        rsi_current = rsi(close_values)
        rsi_previous = rsi(close_values[:-1])
        if rsi_current is None or rsi_previous is None:
            return _blocked("RSI14_UNAVAILABLE")
        atr14 = _atr14_sma(feature_candles["15m"])
        slope_1h = _ema50_slope_atr(feature_candles["1h"])
        slope_4h = _ema50_slope_atr(feature_candles["4h"])
        if atr14 is None or slope_1h is None or slope_4h is None:
            return _blocked("ATR_OR_HTF_EMA_SLOPE_UNAVAILABLE")
        boundary_window = native15[-(RANGE_BOUNDARY_BARS + RANGE_PERSISTENCE_BARS + 1):- (RANGE_PERSISTENCE_BARS + 1)]
        persistence_window = native15[-(RANGE_PERSISTENCE_BARS + 1):-1]
        current = native15[-1]
        prior_high = max(float(candle.high) for candle in boundary_window)
        prior_low = min(float(candle.low) for candle in boundary_window)
        persistence = sum(
            prior_low <= float(candle.close) <= prior_high
            for candle in persistence_window
        ) / RANGE_PERSISTENCE_BARS
        previous_close = float(persistence_window[-1].close)
        config, cost_model_sha256 = _load_simulation_cost_model()
        round_trip_cost = 2.0 * (
            float(config["fee_fraction_per_side"])
            + float(config["slippage_fraction_per_side"])
        )
        features = {
            "as_of_ms": as_of_ms,
            "source_window_sha256": _window_hashes(batches, as_of_ms=as_of_ms),
            "adx14_15m": adx_by_tf["15m"][0],
            "plus_di14_15m": adx_by_tf["15m"][1],
            "minus_di14_15m": adx_by_tf["15m"][2],
            "adx14_1h": adx_by_tf["1h"][0],
            "adx14_4h": adx_by_tf["4h"][0],
            "ema50_slope_atr_1h": slope_1h,
            "ema50_slope_atr_4h": slope_4h,
            "atr14_15m": atr14,
            "range_persistence": persistence,
            "prior_range_high": prior_high,
            "prior_range_low": prior_low,
            "rsi14_previous": rsi_previous,
            "rsi14": rsi_current,
            "mfi14_previous": mfi_values[-2],
            "mfi14": mfi_values[-1],
            "estimated_round_trip_cost_fraction": round_trip_cost,
            "cost_model_status": "ASSUMPTION_BASED",
            "cost_model_sha256": cost_model_sha256,
            "flow_semantics": "MFI14_BASE_VOLUME;TAKER_BUY_UNAVAILABLE",
        }
        if any(type(value) in (int, float) and not math.isfinite(value) for value in features.values()):
            return _blocked("NON_FINITE_RANGE_FEATURE", features=features,
                            cost_model_status="ASSUMPTION_BASED", cost_model_sha256=cost_model_sha256)
        snapshot = RangeSnapshot(
            symbol=SYMBOL, timeframe=SETUP_TIMEFRAME, candle_closed=True,
            observed_at=obs,
            open=float(current.open), high=float(current.high), low=float(current.low),
            close=float(current.close), prior_range_high=prior_high,
            prior_range_low=prior_low, atr14=atr14,
            adx14=adx_by_tf["15m"][0], adx14_1h=adx_by_tf["1h"][0],
            adx14_4h=adx_by_tf["4h"][0], range_persistence=persistence,
            ema50_slope_atr_1h=slope_1h, ema50_slope_atr_4h=slope_4h,
            rsi14_previous=rsi_previous, rsi14=rsi_current,
            mfi14_previous=mfi_values[-2], mfi14=mfi_values[-1],
            estimated_round_trip_cost_fraction=round_trip_cost,
        )
        policy_candidate = evaluate_range_candidate(snapshot)
    except (ArithmeticError, KeyError, TypeError, ValueError, OSError, OverflowError) as exc:
        return _blocked("RANGE_FEATURE_BUILD_FAILED:" + type(exc).__name__ + ":" + str(exc)[:120])

    if policy_candidate.state != "CANDIDATE":
        return StrategyFamilyEvidenceResultV1(
            RANGE_MEAN_REVERSION_RESEARCH_V1.family_id,
            RANGE_MEAN_REVERSION_RESEARCH_V1.version,
            "NO_CANDIDATE", None, (), None, features, policy_candidate.reasons,
            "ASSUMPTION_BASED", cost_model_sha256,
        )

    direction = policy_candidate.direction
    state = "CANDIDATE_LONG" if direction == "LONG" else "CANDIDATE_SHORT"
    evidence_payload = {
        "schema": SCHEMA,
        "version": VERSION,
        "family_id": RANGE_MEAN_REVERSION_RESEARCH_V1.family_id,
        "family_version": RANGE_MEAN_REVERSION_RESEARCH_V1.version,
        "source": SOURCE,
        "symbol": SYMBOL,
        "timeframe": SETUP_TIMEFRAME,
        "regime": "RANGE",
        "direction": direction,
        "state": state,
        "observed_at": obs.isoformat(),
        "policy_version": POLICY_VERSION,
        "features": features,
        "entry_reference": policy_candidate.entry_reference,
        "stop_loss": policy_candidate.stop_loss,
        "take_profit": policy_candidate.take_profit,
        "gross_rr": policy_candidate.gross_rr,
        "net_rr_estimate": policy_candidate.net_rr_estimate,
    }
    try:
        encoded = json.dumps(
            evidence_payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        return _blocked("RANGE_EVIDENCE_CANONICALIZATION_FAILED:" + str(exc)[:120],
                        features=features, cost_model_status="ASSUMPTION_BASED",
                        cost_model_sha256=cost_model_sha256)
    evidence_sha256 = hashlib.sha256(encoded).hexdigest()
    candidate = {
        "source": SOURCE,
        "symbol": SYMBOL,
        "timeframe": SETUP_TIMEFRAME,
        "regime": "RANGE",
        "family_id": RANGE_MEAN_REVERSION_RESEARCH_V1.family_id,
        "family_version": RANGE_MEAN_REVERSION_RESEARCH_V1.version,
        "state": state,
        "direction": direction,
        "observed_at": obs,
        "evidence_sha256": evidence_sha256,
        "policy_version": POLICY_VERSION,
        "entry_reference": policy_candidate.entry_reference,
        "stop_loss": policy_candidate.stop_loss,
        "take_profit": policy_candidate.take_profit,
        "gross_rr": policy_candidate.gross_rr,
        "net_rr_estimate": policy_candidate.net_rr_estimate,
        "cost_model_status": "ASSUMPTION_BASED",
        "cost_model_sha256": cost_model_sha256,
        "flow_semantics": "MFI14_BASE_VOLUME;TAKER_BUY_UNAVAILABLE",
        "execution_enabled": False,
        "orders_placed": False,
        "candidate_generation_authorized": False,
    }
    ref = (
        f"{VERSION};source={SOURCE};symbol={SYMBOL};setup_tf=15m;"
        f"as_of_ms={as_of_ms};evidence_sha256={evidence_sha256};"
        f"cost_model=ASSUMPTION_BASED:{cost_model_sha256}"
    )
    check_refs = {
        "candidate_valid": "candidate_geometry=valid;state=" + state,
        "range_persistence": f"persistence={persistence:.6f};threshold=0.70;prior_only_window=36+12",
        "range_boundary_location": f"prior_low={prior_low};prior_high={prior_high};sweep_reclaim=PASS",
        "reversal_trigger": f"rsi14={rsi_current};rsi14_previous={rsi_previous};mfi14={mfi_values[-1]};mfi14_previous={mfi_values[-2]}",
        "direction_regime_alignment": f"regime=RANGE;direction={direction}",
        "directional_flow_confirmation": "MFI14_BASE_VOLUME;TAKER_BUY_UNAVAILABLE;direction=" + direction,
        "structure_confirmation": "15M_WICK_SWEEP_AND_CLOSE_RECLAIM;" + direction,
        "cost_adjusted_geometry": f"net_rr_estimate={policy_candidate.net_rr_estimate};cost_model=ASSUMPTION_BASED:{cost_model_sha256}",
    }
    checks = tuple(
        ConfirmationCheck(name, "PASS", ref + ";" + check_refs[name], obs)
        for name in (
            "candidate_valid", "range_persistence", "range_boundary_location",
            "reversal_trigger", "direction_regime_alignment",
            "directional_flow_confirmation", "structure_confirmation",
            "cost_adjusted_geometry",
        )
    )
    return StrategyFamilyEvidenceResultV1(
        RANGE_MEAN_REVERSION_RESEARCH_V1.family_id,
        RANGE_MEAN_REVERSION_RESEARCH_V1.version,
        "READY", candidate, checks, evidence_sha256, features, (),
        "ASSUMPTION_BASED", cost_model_sha256,
    )
