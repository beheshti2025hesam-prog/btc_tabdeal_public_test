"""Evidence-only strategy provider built on the canonical Binance Spot OHLCV path.

Reuses the existing native candle adapter and EMA/swing calculators. MFI14 and
ADX14 are implemented here because the repository has no existing implementation
of those indicators. This module never places orders or treats missing evidence
as a pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Sequence

from core.feature_engine.ema import EMACalculator
from core.feature_engine.structure import StructureCalculator
from .confirmation_engine_v1 import ConfirmationCheck
from .market_structure_v1 import SwingPoint, classify_swing_labels, infer_regime
from .native_ohlcv_feature_adapter_v1 import to_feature_batch
from .native_ohlcv_v1 import NativeOHLCVBatch, INTERVAL_MS, validate_native_batch
from .order_block_v1 import OrderBlockResultV1, detect_order_block_v1
from .risk_gate_v1 import RiskCheck
from .strategy_policy_v1 import StrategyEvidenceCheckV1


@dataclass(frozen=True)
class StrategyEvidenceBundleV1:
    observed_at: datetime
    venue: str
    product: str
    symbol: str
    timeframe: str
    regime: str
    direction: str
    structure_labels: tuple[str, ...]
    structure_events: tuple[str, ...]
    strategy_checks: tuple[StrategyEvidenceCheckV1, ...]
    confirmation_checks: tuple[ConfirmationCheck, ...]
    risk_checks: tuple[RiskCheck, ...]
    risk_geometry: tuple[Decimal, Decimal, Decimal] | None
    mfi14: float | None
    adx14: float | None
    plus_di14: float | None
    minus_di14: float | None
    ema50_15m: float | None
    ema50_4h: float | None
    ema200_4h: float | None
    blocked_reasons: tuple[str, ...]
    order_block: OrderBlockResultV1 | None



def _evidence_window_sha256(batch: NativeOHLCVBatch, *, as_of_ms: int) -> str:
    """Hash only the closed candle rows actually eligible at the common as-of."""
    rows = [
        {
            "open_time_ms": candle.open_time_ms,
            "close_time_ms": candle.close_time_ms,
            "open": str(candle.open), "high": str(candle.high),
            "low": str(candle.low), "close": str(candle.close),
            "volume": str(candle.volume), "quote_volume": str(candle.quote_volume),
            "trade_count": candle.trade_count,
            "taker_buy_volume": str(candle.taker_buy_volume),
            "taker_buy_quote_volume": str(candle.taker_buy_quote_volume),
        }
        for candle in batch.candles if candle.close_time_ms < as_of_ms
    ]
    canonical = {
        "venue": batch.venue, "product": batch.product, "symbol": batch.symbol,
        "interval": batch.interval, "as_of_ms": as_of_ms, "candles": rows,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()

def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def mfi14(candles: Sequence) -> float | None:
    """Standard 14-period Money Flow Index using native base-asset volume."""
    if len(candles) < 15:
        return None
    positive = 0.0
    negative = 0.0
    start = len(candles) - 14
    for index in range(start, len(candles)):
        current = candles[index]
        previous = candles[index - 1]
        typical = (float(current.high) + float(current.low) + float(current.close)) / 3.0
        prior_typical = (float(previous.high) + float(previous.low) + float(previous.close)) / 3.0
        flow = typical * float(current.volume)
        if typical > prior_typical:
            positive += flow
        elif typical < prior_typical:
            negative += flow
    if positive == 0 and negative == 0:
        return 50.0
    if negative == 0:
        return 100.0
    if positive == 0:
        return 0.0
    ratio = positive / negative
    return 100.0 - (100.0 / (1.0 + ratio))


def adx14(candles: Sequence) -> tuple[float, float, float] | None:
    """Wilder ADX14 and directional indicators from OHLC only."""
    period = 14
    if len(candles) < (2 * period + 1):
        return None
    true_ranges: list[float] = []
    plus_moves: list[float] = []
    minus_moves: list[float] = []
    for index in range(1, len(candles)):
        current, previous = candles[index], candles[index - 1]
        up = float(current.high) - float(previous.high)
        down = float(previous.low) - float(current.low)
        plus_moves.append(up if up > down and up > 0 else 0.0)
        minus_moves.append(down if down > up and down > 0 else 0.0)
        true_ranges.append(max(
            float(current.high) - float(current.low),
            abs(float(current.high) - float(previous.close)),
            abs(float(current.low) - float(previous.close)),
        ))
    smoothed_tr = sum(true_ranges[:period])
    smoothed_plus = sum(plus_moves[:period])
    smoothed_minus = sum(minus_moves[:period])
    dx_values: list[float] = []
    latest_plus_di = latest_minus_di = 0.0
    for index in range(period - 1, len(true_ranges)):
        if index > period - 1:
            smoothed_tr = smoothed_tr - smoothed_tr / period + true_ranges[index]
            smoothed_plus = smoothed_plus - smoothed_plus / period + plus_moves[index]
            smoothed_minus = smoothed_minus - smoothed_minus / period + minus_moves[index]
        if smoothed_tr <= 0:
            latest_plus_di = latest_minus_di = 0.0
        else:
            latest_plus_di = 100.0 * smoothed_plus / smoothed_tr
            latest_minus_di = 100.0 * smoothed_minus / smoothed_tr
        denominator = latest_plus_di + latest_minus_di
        dx_values.append(100.0 * abs(latest_plus_di - latest_minus_di) / denominator if denominator else 0.0)
    if len(dx_values) < period:
        return None
    adx_value = sum(dx_values[:period]) / period
    for dx in dx_values[period:]:
        adx_value = ((adx_value * (period - 1)) + dx) / period
    return adx_value, latest_plus_di, latest_minus_di


def _swing_labels(candles: Sequence) -> tuple[tuple[str, ...], object | None]:
    snapshots = StructureCalculator(left=2, right=2).calculate(candles)
    changes: list[tuple[datetime, str, Decimal]] = []
    seen_high = seen_low = None
    for snap in snapshots:
        high_stamp = snap.swing_high_timestamp
        low_stamp = snap.swing_low_timestamp
        if snap.swing_high is not None and high_stamp is not None and high_stamp != seen_high:
            changes.append((_aware_utc(high_stamp), "SWING_HIGH", Decimal(str(snap.swing_high))))
            seen_high = high_stamp
        if snap.swing_low is not None and low_stamp is not None and low_stamp != seen_low:
            changes.append((_aware_utc(low_stamp), "SWING_LOW", Decimal(str(snap.swing_low))))
            seen_low = low_stamp
    changes.sort(key=lambda item: (item[0], item[1]))
    swings: list[SwingPoint] = []
    labels: list[str] = []
    for sequence, (stamp, kind, price) in enumerate(changes, start=1):
        swing = SwingPoint(kind, price, stamp, sequence)
        labels.extend(classify_swing_labels(swings, swing))
        swings.append(swing)
    return tuple(labels), (snapshots[-1] if snapshots else None)


class StrategyEvidenceProviderV1:
    """Create versioned, causal evidence from one canonical market-data source."""

    VERSION = "hes-native-strategy-evidence-v1"
    ADX_MINIMUM = 20.0
    MINIMUM_HTF_CANDLES = 200
    MAX_SOURCE_FETCH_SKEW_MS = 300_000

    @staticmethod
    def _check(name, state, ref, digest, observed_at):
        return StrategyEvidenceCheckV1(
            name=name, state=state, evidence_ref=ref, evidence_sha256=digest,
            provider=StrategyEvidenceProviderV1.VERSION, provider_version="1",
            observed_at=observed_at,
        )

    @staticmethod
    def _confirmation(name, state, ref, observed_at):
        return ConfirmationCheck(name, state, ref, observed_at)

    @staticmethod
    def _risk(name, state, ref, observed_at):
        return RiskCheck(name, state, ref, observed_at)

    def evaluate(
        self,
        *,
        candles_15m: NativeOHLCVBatch,
        candles_4h: NativeOHLCVBatch,
        now_ms: int,
        vwap: float | None = None,
    ) -> StrategyEvidenceBundleV1:
        validate_native_batch(candles_15m)
        validate_native_batch(candles_4h)
        expected = ("binance", "spot", "BTCUSDT")
        if (candles_15m.venue, candles_15m.product, candles_15m.symbol) != expected:
            raise ValueError("unsupported 15m strategy source scope")
        if (candles_4h.venue, candles_4h.product, candles_4h.symbol) != expected:
            raise ValueError("unsupported 4h strategy source scope")
        if candles_15m.interval != "15m" or candles_4h.interval != "4h":
            raise ValueError("strategy provider requires 15m and 4h batches")
        if type(now_ms) is not int or now_ms < 0:
            raise ValueError("now_ms must be a non-negative integer")

        as_of_ms = min(candles_15m.fetched_at_ms, candles_4h.fetched_at_ms)
        observed_at = datetime.fromtimestamp(as_of_ms / 1000, tz=timezone.utc)
        if as_of_ms > now_ms + 60_000:
            raise ValueError("strategy observation time is ahead of current UTC")
        stale = []
        for batch in (candles_15m, candles_4h):
            interval_ms = INTERVAL_MS[batch.interval]
            eligible = tuple(c for c in batch.candles if c.close_time_ms < as_of_ms)
            if not eligible or now_ms - eligible[-1].close_time_ms > interval_ms + 60_000:
                stale.append(batch.interval)
        if abs(candles_15m.fetched_at_ms - candles_4h.fetched_at_ms) > self.MAX_SOURCE_FETCH_SKEW_MS:
            stale.append("SOURCE_FETCH_SKEW")
        gaps = bool(candles_15m.gaps or candles_4h.gaps)
        feature_15m = to_feature_batch(candles_15m, as_of_ms=as_of_ms, now_ms=max(now_ms, as_of_ms))
        feature_4h = to_feature_batch(candles_4h, as_of_ms=as_of_ms, now_ms=max(now_ms, as_of_ms))
        c15 = feature_15m.candles
        c4 = feature_4h.candles
        native15 = tuple(c for c in candles_15m.candles if c.close_time_ms < as_of_ms)
        digest_15m = _evidence_window_sha256(candles_15m, as_of_ms=as_of_ms)
        digest_4h = _evidence_window_sha256(candles_4h, as_of_ms=as_of_ms)
        blocked: list[str] = []
        if stale:
            blocked.append("STRATEGY_SOURCE_STALE:" + ",".join(stale))
        if gaps:
            blocked.append("STRATEGY_SOURCE_GAPS_PRESENT")

        ema50_15_points = EMACalculator(50).calculate(c15)
        ema50_4_points = EMACalculator(50).calculate(c4)
        ema200_4_points = EMACalculator(200).calculate(c4)
        ema50_15 = ema50_15_points[-1].value if ema50_15_points else None
        ema50_4 = ema50_4_points[-1].value if ema50_4_points else None
        ema200_4 = ema200_4_points[-1].value if ema200_4_points else None
        mfi_value = mfi14(native15)
        adx_values = adx14(native15)
        adx_value, plus_di, minus_di = adx_values if adx_values else (None, None, None)
        labels, structure_snapshot = _swing_labels(c15)
        structure_regime = infer_regime(labels)
        latest_native = native15[-1] if native15 else None
        previous_native = native15[-2] if len(native15) >= 2 else None
        htf_direction = "UNKNOWN"
        if len(c4) >= self.MINIMUM_HTF_CANDLES and ema50_4 is not None and ema200_4 is not None:
            last4_close = c4[-1].close
            if last4_close > ema200_4 and ema50_4 > ema200_4:
                htf_direction = "BULLISH"
            elif last4_close < ema200_4 and ema50_4 < ema200_4:
                htf_direction = "BEARISH"
        direction = "UNKNOWN"
        regime = "UNKNOWN"
        if htf_direction == "BULLISH" and structure_regime == "UPTREND":
            direction, regime = "BULLISH", "UPTREND"
        elif htf_direction == "BEARISH" and structure_regime == "DOWNTREND":
            direction, regime = "BEARISH", "DOWNTREND"

        last_high = getattr(structure_snapshot, "swing_high", None)
        last_low = getattr(structure_snapshot, "swing_low", None)
        previous_close = float(previous_native.close) if previous_native else None
        current_close = float(latest_native.close) if latest_native else None
        break_direction = htf_direction if htf_direction in ("BULLISH", "BEARISH") else direction
        bullish_break = bool(break_direction == "BULLISH" and last_high is not None and previous_close is not None
                             and current_close is not None and previous_close <= last_high < current_close)
        bearish_break = bool(break_direction == "BEARISH" and last_low is not None and previous_close is not None
                             and current_close is not None and previous_close >= last_low > current_close)
        break_type = "CHOCH" if (
            (bullish_break and structure_regime == "DOWNTREND")
            or (bearish_break and structure_regime == "UPTREND")
        ) else "BOS"
        structure_events: tuple[str, ...] = (break_type,) if bullish_break or bearish_break else (labels[-2:] if labels else ())
        order_block = detect_order_block_v1(
            native15,
            direction=break_direction,
            break_confirmed=bool(bullish_break or bearish_break),
            break_type=break_type,
            htf_direction=htf_direction,
            last_swing_high=Decimal(str(last_high)) if last_high is not None else None,
            last_swing_low=Decimal(str(last_low)) if last_low is not None else None,
            ema50=ema50_15,
            vwap=vwap,
            source_response_sha256=candles_15m.response_sha256,
        )

        pullback = None
        if direction != "UNKNOWN" and latest_native is not None and ema50_15 is not None:
            if direction == "BULLISH":
                pullback = (float(latest_native.low) <= ema50_15 < float(latest_native.close)
                            or (last_high is not None and float(latest_native.low) <= last_high < float(latest_native.close)))
            else:
                pullback = (float(latest_native.high) >= ema50_15 > float(latest_native.close)
                            or (last_low is not None and float(latest_native.high) >= last_low > float(latest_native.close)))

        def state_or_unknown(value):
            if value is None or stale or gaps:
                return "UNKNOWN"
            return "PASS" if value else "FAIL"

        htf_ok = None if htf_direction == "UNKNOWN" or direction == "UNKNOWN" else htf_direction == direction
        mfi_ok = None if mfi_value is None or direction == "UNKNOWN" else (
            mfi_value > 50.0 if direction == "BULLISH" else mfi_value < 50.0
        )
        adx_ok = None if adx_value is None or plus_di is None or minus_di is None or direction == "UNKNOWN" else (
            adx_value >= self.ADX_MINIMUM and plus_di > minus_di if direction == "BULLISH"
            else adx_value >= self.ADX_MINIMUM and minus_di > plus_di
        )
        break_ok = None if structure_snapshot is None or direction == "UNKNOWN" else (bullish_break if direction == "BULLISH" else bearish_break)
        geometry = None
        geometry_ok = None
        if latest_native is not None and current_close is not None and current_close > 0:
            entry = Decimal(str(latest_native.close))
            stop_value = last_low if direction == "BULLISH" else last_high if direction == "BEARISH" else None
            if stop_value is not None:
                stop = Decimal(str(stop_value))
                if (direction == "BULLISH" and Decimal("0") < stop < entry) or (
                    direction == "BEARISH" and Decimal("0") < entry < stop
                ):
                    risk_distance = entry - stop if direction == "BULLISH" else stop - entry
                    target = entry + Decimal("3") * risk_distance if direction == "BULLISH" else entry - Decimal("3") * risk_distance
                    if target > 0:
                        geometry = (entry, stop, target)
                        geometry_ok = True

        if stale or gaps:
            strategy_checks = []
            for name in ("htf_trend_alignment", "pullback_location", "reversal_break_confirmation",
                         "mfi_confirmation", "adx_directional_strength", "risk_geometry_3_to_1"):
                digest = digest_4h if name == "htf_trend_alignment" else digest_15m
                raw_digest = candles_4h.response_sha256 if name == "htf_trend_alignment" else candles_15m.response_sha256
                ref = f"{name}:raw-sha256={raw_digest}:as-of-ms={as_of_ms}:window-sha256={digest}"
                strategy_checks.append(self._check(name, "UNKNOWN", ref, digest, observed_at))
        else:
            strategy_checks = [
                self._check("htf_trend_alignment", state_or_unknown(htf_ok),
                            f"4h:raw-sha256={candles_4h.response_sha256}:as-of-ms={as_of_ms}:window-sha256={digest_4h}", digest_4h, observed_at),
                self._check("pullback_location", state_or_unknown(pullback),
                            f"15m:raw-sha256={candles_15m.response_sha256}:as-of-ms={as_of_ms}:window-sha256={digest_15m}", digest_15m, observed_at),
                self._check("reversal_break_confirmation", state_or_unknown(break_ok),
                            f"15m:raw-sha256={candles_15m.response_sha256}:as-of-ms={as_of_ms}:window-sha256={digest_15m}", digest_15m, observed_at),
                self._check("mfi_confirmation", state_or_unknown(mfi_ok),
                            f"15m:raw-sha256={candles_15m.response_sha256}:as-of-ms={as_of_ms}:window-sha256={digest_15m}", digest_15m, observed_at),
                self._check("adx_directional_strength", state_or_unknown(adx_ok),
                            f"15m:raw-sha256={candles_15m.response_sha256}:as-of-ms={as_of_ms}:window-sha256={digest_15m}", digest_15m, observed_at),
                self._check("risk_geometry_3_to_1", state_or_unknown(geometry_ok),
                            f"15m:raw-sha256={candles_15m.response_sha256}:as-of-ms={as_of_ms}:window-sha256={digest_15m}", digest_15m, observed_at),
            ]

        if direction == "UNKNOWN" or regime == "UNKNOWN":
            blocked.append("HTF_AND_STRUCTURE_DIRECTION_NOT_ALIGNED")
        if geometry is None:
            blocked.append("STRUCTURE_BASED_RISK_GEOMETRY_UNAVAILABLE")
        ref = "strategy-provider-v1:" + candles_15m.response_sha256
        direction_state = "PASS" if direction != "UNKNOWN" and regime in ("UPTREND", "DOWNTREND") else "UNKNOWN"
        candidate_state = "PASS" if direction_state == "PASS" and len(labels) >= 2 else "UNKNOWN"
        structure_state = "PASS" if labels else "UNKNOWN"
        confirmation_checks = (
            self._confirmation("structure_direction_aligned", direction_state, ref, observed_at),
            self._confirmation("candidate_valid", candidate_state, ref, observed_at),
            self._confirmation("direction_regime_alignment", direction_state, ref, observed_at),
            self._confirmation("structural_event_present", structure_state, ref, observed_at),
        )
        geometry_state = "PASS" if geometry is not None else "UNKNOWN"
        risk_checks = (
            self._risk("confirmation_valid", direction_state, ref, observed_at),
            self._risk("risk_context_available", "UNKNOWN", ref, observed_at),
            self._risk("entry_stop_target_geometry_valid", geometry_state, ref, observed_at),
            self._risk("risk_reward_gate_passed", geometry_state, ref, observed_at),
            self._risk("execution_disabled", "PASS", ref, observed_at),
        )
        return StrategyEvidenceBundleV1(
            observed_at=observed_at, venue=candles_15m.venue, product=candles_15m.product,
            symbol=candles_15m.symbol, timeframe=candles_15m.interval, regime=regime,
            direction=direction, structure_labels=labels, structure_events=structure_events,
            strategy_checks=tuple(strategy_checks), confirmation_checks=confirmation_checks,
            risk_checks=risk_checks, risk_geometry=geometry, mfi14=mfi_value, adx14=adx_value,
            plus_di14=plus_di, minus_di14=minus_di, ema50_15m=ema50_15, ema50_4h=ema50_4,
            ema200_4h=ema200_4, blocked_reasons=tuple(dict.fromkeys(blocked)), order_block=order_block,
        )
