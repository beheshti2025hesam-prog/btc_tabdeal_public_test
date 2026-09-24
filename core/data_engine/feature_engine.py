"""Mother Agent - Feature Engine v1.0

Combines already-computed descriptive intelligence into a deterministic,
exchange-independent feature snapshot. This layer does not generate trades.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from core.data_engine.ema import EMAValue
from core.data_engine.pressure import BuySellPressure
from core.data_engine.regime import MarketRegime
from core.data_engine.volatility import VolatilitySnapshot
from core.data_engine.volume import VolumeSnapshot
from core.data_engine.vwap import VWAPSnapshot


@dataclass(frozen=True)
class FeatureSnapshot:
    symbol: str
    timestamp: Optional[datetime]
    timeframe_seconds: int
    close: Optional[float]
    ema: Optional[float]
    vwap: Optional[float]
    buy_sell_delta: Optional[float]
    buy_ratio: Optional[float]
    realized_volatility: Optional[float]
    average_true_range: Optional[float]
    volume_ratio: Optional[float]
    volume_spike: Optional[bool]
    regime: Optional[str]


class FeatureEngine:
    """Build a single immutable feature snapshot from intelligence outputs."""

    def build(
        self,
        *,
        symbol: str,
        timeframe_seconds: int,
        timestamp: Optional[datetime] = None,
        close: Optional[float] = None,
        ema: Optional[EMAValue] = None,
        vwap: Optional[VWAPSnapshot] = None,
        pressure: Optional[BuySellPressure] = None,
        volatility: Optional[VolatilitySnapshot] = None,
        volume: Optional[VolumeSnapshot] = None,
        regime: Optional[MarketRegime] = None,
    ) -> FeatureSnapshot:
        if ema and (ema.symbol != symbol or ema.timeframe_seconds != timeframe_seconds):
            raise ValueError("EMA does not match symbol/timeframe")
        if volatility and (
            volatility.symbol != symbol
            or volatility.timeframe_seconds != timeframe_seconds
        ):
            raise ValueError("volatility does not match symbol/timeframe")
        if volume and (
            volume.symbol != symbol
            or volume.timeframe_seconds != timeframe_seconds
        ):
            raise ValueError("volume does not match symbol/timeframe")
        if regime and (
            regime.symbol != symbol
            or regime.timeframe_seconds != timeframe_seconds
        ):
            raise ValueError("regime does not match symbol/timeframe")
        if vwap and vwap.symbol != symbol:
            raise ValueError("VWAP does not match symbol")
        if pressure and pressure.symbol != symbol:
            raise ValueError("pressure does not match symbol")

        return FeatureSnapshot(
            symbol=symbol,
            timestamp=timestamp,
            timeframe_seconds=timeframe_seconds,
            close=close,
            ema=ema.value if ema else None,
            vwap=vwap.vwap if vwap else None,
            buy_sell_delta=pressure.delta if pressure else None,
            buy_ratio=pressure.buy_ratio if pressure else None,
            realized_volatility=(
                volatility.realized_volatility if volatility else None
            ),
            average_true_range=(
                volatility.average_true_range if volatility else None
            ),
            volume_ratio=volume.latest_vs_average if volume else None,
            volume_spike=volume.is_volume_spike if volume else None,
            regime=regime.label if regime else None,
        )
