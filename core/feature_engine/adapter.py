"""HES Trade Agent - Data Intelligence -> Feature Engine adapter v1.

Explicit boundary from descriptive, window-aligned intelligence to FeatureSnapshot.
No signals, ranking, orders, or execution.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from core.data_engine.candles import Candle
from core.data_engine.pressure import BuySellPressure
from core.data_engine.volume import VolumeSnapshot
from core.data_engine.volatility import VolatilitySnapshot
from core.data_engine.regime import MarketRegime
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
    pressure: BuySellPressure | None = None
    volume: VolumeSnapshot | None = None
    volatility: VolatilitySnapshot | None = None
    market_regime: MarketRegime | None = None


class DataIntelligenceFeatureAdapter:
    """Build a FeatureSnapshot only from temporally aligned intelligence."""

    @staticmethod
    def _matches_window(item, candle: Candle) -> bool:
        return (
            item.symbol == candle.symbol
            and item.timeframe_seconds == candle.timeframe_seconds
            and item.window_start == candle.start.astimezone(timezone.utc)
            and item.window_end == candle.end.astimezone(timezone.utc)
        )

    def build(self, item: IntelligenceFeatureInput) -> FeatureSnapshot:
        candle, ema, vwap = item.candle, item.ema, item.vwap

        if not candle.symbol or not ema.symbol or not vwap.symbol:
            raise ValueError("intelligence symbols must be non-empty")
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
        if not vwap.vwap > 0:
            raise ValueError("VWAP must be positive")

        if item.pressure is not None and not self._matches_window(item.pressure, candle):
            raise ValueError("pressure window does not match candle window")
        if item.volume is not None and not self._matches_window(item.volume, candle):
            raise ValueError("volume window does not match candle window")
        if item.volatility is not None and not self._matches_window(item.volatility, candle):
            raise ValueError("volatility window does not match candle window")
        if item.market_regime is not None and not self._matches_window(item.market_regime, candle):
            raise ValueError("regime window does not match candle window")

        delta = item.pressure.delta if item.pressure is not None else item.buy_sell_delta
        buy_ratio = item.pressure.buy_ratio if item.pressure is not None else item.buy_ratio
        volume_ratio = item.volume.latest_vs_average if item.volume is not None else item.volume_ratio
        volume_spike = item.volume.is_volume_spike if item.volume is not None else item.volume_spike
        realized_volatility = (
            item.volatility.realized_volatility
            if item.volatility is not None else item.realized_volatility
        )
        atr = item.volatility.average_true_range if item.volatility is not None else item.average_true_range
        regime = item.market_regime.label if item.market_regime is not None else item.regime

        return FeatureSnapshot(
            symbol=candle.symbol,
            timeframe_seconds=candle.timeframe_seconds,
            close=candle.close,
            ema=ema.value,
            vwap=vwap.vwap,
            buy_sell_delta=delta,
            buy_ratio=buy_ratio,
            realized_volatility=realized_volatility,
            average_true_range=atr,
            volume_ratio=volume_ratio,
            volume_spike=volume_spike,
            regime=regime,
            timestamp=candle_end,
        )
