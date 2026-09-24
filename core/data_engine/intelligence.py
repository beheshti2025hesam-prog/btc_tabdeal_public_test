"""
Mother Agent - Data Intelligence Interface
Data Foundation v1.1

Produces deterministic OHLCV candles from the canonical trade layer.
"""

from core.data_engine.candles import Candle, TradeCandleAggregator

__all__ = ["Candle", "TradeCandleAggregator"]
