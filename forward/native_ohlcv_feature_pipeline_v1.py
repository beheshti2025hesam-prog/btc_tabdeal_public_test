"""Native OHLCV to descriptive feature snapshot; no strategy or execution."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone

from core.data_engine.regime import MarketRegimeClassifier
from core.data_engine.volatility import VolatilityCalculator
from core.data_engine.volume import VolumeIntelligenceCalculator
from core.feature_engine.ema import EMACalculator
from core.feature_engine.momentum import MomentumCalculator
from core.feature_engine.quality import FeatureQualityGate, FeatureQualityResult, FeatureSnapshot
from core.feature_engine.structure import StructureCalculator

from .native_ohlcv_feature_adapter_v1 import NativeOHLCVFeatureBatch, to_feature_batch
from .native_ohlcv_v1 import NativeOHLCVBatch


@dataclass(frozen=True)
class NativeOHLCVFeatureResult:
    venue: str
    product: str
    symbol: str
    interval: str
    source_response_sha256: str
    as_of_ms: int
    candle_count: int
    gaps: tuple
    snapshot: FeatureSnapshot
    quality: FeatureQualityResult
    ema_points: int
    momentum_points: int
    structure_points: int
    decision_ready: bool
    reason: str


class NativeOHLCVFeaturePipelineV1:
    """Build existing descriptive feature inputs from native venue candles only."""

    def __init__(
        self,
        *,
        ema_period: int = 20,
        vwap_period: int = 20,
        momentum_period: int = 10,
        volume_spike_multiplier: float = 1.5,
    ) -> None:
        if type(ema_period) is not int or ema_period <= 0:
            raise ValueError("ema_period must be a positive integer")
        if type(vwap_period) is not int or vwap_period <= 0:
            raise ValueError("vwap_period must be a positive integer")
        if type(momentum_period) is not int or momentum_period <= 0:
            raise ValueError("momentum_period must be a positive integer")
        self.ema_period = ema_period
        self.vwap_period = vwap_period
        self.momentum_period = momentum_period
        self.ema = EMACalculator(ema_period)
        self.momentum = MomentumCalculator(momentum_period)
        self.structure = StructureCalculator()
        self.volume = VolumeIntelligenceCalculator(volume_spike_multiplier)
        self.volatility = VolatilityCalculator()
        self.regime = MarketRegimeClassifier()
        self.quality_gate = FeatureQualityGate(require_ema=True, require_vwap=True)

    def build(
        self,
        batch: NativeOHLCVBatch,
        *,
        as_of_ms: int | None = None,
        now_ms: int | None = None,
    ) -> NativeOHLCVFeatureResult:
        feature_batch: NativeOHLCVFeatureBatch = to_feature_batch(
            batch, as_of_ms=as_of_ms, now_ms=now_ms
        )
        candles = feature_batch.candles
        eligible_native = tuple(
            c for c in batch.candles if c.close_time_ms < feature_batch.as_of_ms
        )

        ema_points = self.ema.calculate(candles)
        momentum_points = self.momentum.calculate(candles)
        structure_points = self.structure.calculate(candles)
        volume_points = self.volume.calculate(candles)
        volatility_points = self.volatility.calculate(candles)
        regime_points = self.regime.classify(candles)

        ema_value = ema_points[-1].value if ema_points else None
        latest_close = candles[-1].close if candles else None
        timestamp = candles[-1].end if candles else None

        vwap = None
        buy_ratio = None
        buy_sell_delta = None
        if len(eligible_native) >= self.vwap_period:
            window = eligible_native[-self.vwap_period:]
            total_base = sum((c.volume for c in window), Decimal("0"))
            total_quote = sum((c.quote_volume for c in window), Decimal("0"))
            total_taker_buy = sum((c.taker_buy_volume for c in window), Decimal("0"))
            if total_base > 0:
                vwap = float(total_quote / total_base)
                buy_ratio = float(total_taker_buy / total_base)
                buy_sell_delta = float((Decimal("2") * total_taker_buy) - total_base)

        volume_ratio = volume_points[-1].latest_vs_average if volume_points else None
        volume_spike = volume_points[-1].is_volume_spike if volume_points else None
        realized_volatility = volatility_points[-1].realized_volatility if volatility_points else None
        average_true_range = volatility_points[-1].average_true_range if volatility_points else None
        regime = regime_points[-1].label if regime_points else None

        snapshot = FeatureSnapshot(
            symbol=batch.symbol,
            timeframe_seconds=feature_batch.timeframe_seconds,
            close=latest_close,
            ema=ema_value,
            vwap=vwap,
            buy_sell_delta=buy_sell_delta,
            buy_ratio=buy_ratio,
            realized_volatility=realized_volatility,
            average_true_range=average_true_range,
            volume_ratio=volume_ratio,
            volume_spike=volume_spike,
            regime=regime,
            timestamp=timestamp,
        )
        quality = self.quality_gate.evaluate(snapshot)
        minimum = max(self.ema_period, self.vwap_period)
        if len(candles) < minimum:
            ready, reason = False, "INSUFFICIENT_CLOSED_CANDLES"
        elif feature_batch.gaps:
            ready, reason = False, "OBSERVED_CANDLE_GAPS"
        elif not quality.passed:
            ready, reason = False, "FEATURE_QUALITY_REJECTED"
        else:
            ready, reason = True, "NATIVE_OHLCV_FEATURES_READY"

        return NativeOHLCVFeatureResult(
            venue=batch.venue,
            product=batch.product,
            symbol=batch.symbol,
            interval=batch.interval,
            source_response_sha256=feature_batch.source_response_sha256,
            as_of_ms=feature_batch.as_of_ms,
            candle_count=len(candles),
            gaps=feature_batch.gaps,
            snapshot=snapshot,
            quality=quality,
            ema_points=len(ema_points),
            momentum_points=len(momentum_points),
            structure_points=len(structure_points),
            decision_ready=ready,
            reason=reason,
        )
