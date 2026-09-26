"""HES Trade Agent - Data Intelligence -> Feature Engine adapter v1.

This adapter is the explicit contract boundary from descriptive Data Intelligence
outputs to FeatureSnapshot. It only combines already-computed, window-aligned
inputs; it does not generate signals, rank opportunities, or execute orders.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from core.data_engine.candles import Candle
from core.data_engine.vwap import VWAPSnapshot
from core.feature_engine.ema import EMASnapshot
from core.feature_engine.quality import FeatureSnapshot
from core.feature_engine.temporal import FeatureTemporalAlignment, FeatureTemporalInput


@dataclass(frozen=True)
class IntelligenceFeatureInput:
    candle: Candle
    ema: EMASnapshot
    vwap: VWAPSnapshot
    buy_sell_delta: float | None = None
    buy_ratio: float | None = None
    realized_volatility: float | None = None
    average_true_range: float | None = None
    volume_ratio: float | None = None
    volume_spike: bool | None = None
    regime: str | None = None


class DataIntelligenceFeatureAdapter:
    """Build a FeatureSnapshot only from temporally aligned intelligence."""

    def build(self, item: IntelligenceFeatureInput) -> FeatureSnapshot:
        candle = item.candle
        ema = item.ema
        vwap = item.vwap

        for name, symbol in (("candle", candle.symbol), ("ema", ema.symbol), ("vwap", vwap.symbol)):
            if not symbol:
                raise ValueError(f"{name} symbol must be non-empty")
        if candle.symbol != ema.symbol or candle.symbol != vwap.symbol:
            raise ValueError("intelligence symbols must match")
        if candle.timeframe_seconds != ema.timeframe_seconds:
            raise ValueError("candle/EMA timeframe mismatch")
        if candle.timeframe_seconds != vwap.timeframe_seconds:
            raise ValueError("candle/VWAP timeframe mismatch")

        candle_start = candle.start.astimezone(timezone.utc)
        candle_end = candle.end.astimezone(timezone.utc)
        ema_timestamp = ema.timestamp.astimezone(timezone.utc)
        vwap_start = vwap.start.astimezone(timezone.utc)
        vwap_end = vwap.end.astimezone(timezone.utc)

        temporal_violations = FeatureTemporalAlignment().validate(
            FeatureTemporalInput(
                symbol=candle.symbol,
                timeframe_seconds=candle.timeframe_seconds,
                window_start=candle_start,
                window_end=candle_end,
                feature_timestamp=candle_end,
                source="data_intelligence",
                source_timestamp=candle_end,
            )
        )
        if temporal_violations:
            raise ValueError("temporal alignment failed: " + ", ".join(temporal_violations))
        if ema_timestamp != candle_end:
            raise ValueError("EMA timestamp does not match candle window end")
        if vwap_start != candle_start or vwap_end != candle_end:
            raise ValueError("VWAP window does not match candle window")
        if ema.period <= 0:
            raise ValueError("EMA period must be positive")
        if not item.vwap.vwap > 0:
            raise ValueError("VWAP must be positive")

        return FeatureSnapshot(
            symbol=candle.symbol,
            timeframe_seconds=candle.timeframe_seconds,
            close=candle.close,
            ema=ema.value,
            vwap=vwap.vwap,
            buy_sell_delta=item.buy_sell_delta,
            buy_ratio=item.buy_ratio,
            realized_volatility=item.realized_volatility,
            average_true_range=item.average_true_range,
            volume_ratio=item.volume_ratio,
            volume_spike=item.volume_spike,
            regime=item.regime,
            timestamp=candle_end,
        )
