"""Boundary tests for Data Intelligence -> Feature Engine adaptation."""
import unittest
from datetime import datetime, timedelta, timezone

from core.data_engine.candles import Candle
from core.data_engine.vwap import VWAPSnapshot

from core.data_engine.pressure import BuySellPressure
from core.data_engine.volume import VolumeSnapshot
from core.data_engine.volatility import VolatilitySnapshot
from core.data_engine.regime import MarketRegime
from core.feature_engine.adapter import (
    DataIntelligenceFeatureAdapter,
    IntelligenceFeatureInput,
)
from core.feature_engine.ema import EMASnapshot


class DataIntelligenceFeatureAdapterTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
        self.end = self.start + timedelta(minutes=1)
        self.candle = Candle("BTC_USDT", 60, self.start, self.end, 100, 105, 99, 103, 12, 3)
        self.ema = EMASnapshot("BTC_USDT", 60, 20, self.end, 101)
        self.vwap = VWAPSnapshot("BTC_USDT", 60, self.start, self.end, 12, 102, 3)

    def item(self, **overrides):
        values = dict(candle=self.candle, ema=self.ema, vwap=self.vwap)
        values.update(overrides)
        return IntelligenceFeatureInput(**values)

    def test_builds_aligned_snapshot(self):
        snapshot = DataIntelligenceFeatureAdapter().build(self.item(buy_ratio=0.6))
        self.assertEqual(snapshot.symbol, "BTC_USDT")
        self.assertEqual(snapshot.timestamp, self.end)
        self.assertEqual(snapshot.ema, 101)
        self.assertEqual(snapshot.vwap, 102)
        self.assertEqual(snapshot.buy_ratio, 0.6)

    def test_rejects_symbol_mismatch(self):
        bad = EMASnapshot("ETH_USDT", 60, 20, self.end, 101)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(self.item(ema=bad))

    def test_rejects_timeframe_mismatch(self):
        bad = EMASnapshot("BTC_USDT", 300, 20, self.end, 101)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(self.item(ema=bad))

    def test_rejects_ema_timestamp_mismatch(self):
        bad = EMASnapshot("BTC_USDT", 60, 20, self.start, 101)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(self.item(ema=bad))

    def test_builds_from_windowed_intelligence(self):
        pressure = BuySellPressure("BTC_USDT", 60, self.start, self.end, 8, 4, 12, 4, 2/3, 1/3, 5, 3)
        volume = VolumeSnapshot("BTC_USDT", 60, self.start, self.end, 5, 60, 12, 2, 16, 4/3, False)
        volatility = VolatilitySnapshot("BTC_USDT", 60, self.start, self.end, 5, 0.01, 0.02, 0.04, 1.2)
        regime = MarketRegime("BTC_USDT", 60, self.start, self.end, "uptrend", 5, 0.03, 2.0)
        snapshot = DataIntelligenceFeatureAdapter().build(
            self.item(pressure=pressure, volume=volume, volatility=volatility, market_regime=regime)
        )
        self.assertEqual(snapshot.buy_sell_delta, 4)
        self.assertEqual(snapshot.buy_ratio, 2/3)
        self.assertEqual(snapshot.volume_ratio, 4/3)
        self.assertFalse(snapshot.volume_spike)
        self.assertEqual(snapshot.realized_volatility, 0.04)
        self.assertEqual(snapshot.average_true_range, 1.2)
        self.assertEqual(snapshot.regime, "uptrend")

    def test_rejects_windowed_pressure_mismatch(self):
        bad = BuySellPressure("BTC_USDT", 60, self.start + timedelta(minutes=1), self.end + timedelta(minutes=1),
                              8, 4, 12, 4, 2/3, 1/3, 5, 3)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(self.item(pressure=bad))

    def _windowed(self):
        pressure = BuySellPressure("BTC_USDT", 60, self.start, self.end, 8, 4, 12, 4, 2/3, 1/3, 5, 3)
        volume = VolumeSnapshot("BTC_USDT", 60, self.start, self.end, 5, 60, 12, 2, 16, 4/3, False)
        volatility = VolatilitySnapshot("BTC_USDT", 60, self.start, self.end, 5, 0.01, 0.02, 0.04, 1.2)
        regime = MarketRegime("BTC_USDT", 60, self.start, self.end, "uptrend", 5, 0.03, 2.0)
        return pressure, volume, volatility, regime

    def test_rejects_windowed_symbol_mismatch(self):
        pressure, volume, volatility, regime = self._windowed()
        bad = BuySellPressure("ETH_USDT", 60, self.start, self.end, 8, 4, 12, 4, 2/3, 1/3, 5, 3)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(
                self.item(pressure=bad, volume=volume, volatility=volatility, market_regime=regime)
            )

    def test_rejects_windowed_timeframe_mismatch(self):
        pressure, volume, volatility, regime = self._windowed()
        bad = VolumeSnapshot("BTC_USDT", 300, self.start, self.end, 5, 60, 12, 2, 16, 4/3, False)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(
                self.item(pressure=pressure, volume=bad, volatility=volatility, market_regime=regime)
            )

    def test_rejects_windowed_end_mismatch(self):
        pressure, volume, volatility, regime = self._windowed()
        bad = VolatilitySnapshot("BTC_USDT", 60, self.start, self.end + timedelta(minutes=1),
                                 5, 0.01, 0.02, 0.04, 1.2)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(
                self.item(pressure=pressure, volume=volume, volatility=bad, market_regime=regime)
            )

    def test_rejects_windowed_regime_start_mismatch(self):
        pressure, volume, volatility, regime = self._windowed()
        bad = MarketRegime("BTC_USDT", 60, self.start - timedelta(minutes=1), self.end - timedelta(minutes=1),
                           "uptrend", 5, 0.03, 2.0)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(
                self.item(pressure=pressure, volume=volume, volatility=volatility, market_regime=bad)
            )

    def test_accepts_equivalent_timezone_window(self):
        offset = timezone(timedelta(hours=2))
        pressure = BuySellPressure("BTC_USDT", 60, self.start.astimezone(offset), self.end.astimezone(offset),
                                   8, 4, 12, 4, 2/3, 1/3, 5, 3)
        snapshot = DataIntelligenceFeatureAdapter().build(self.item(pressure=pressure))
        self.assertEqual(snapshot.buy_sell_delta, 4)

    def test_rejects_vwap_window_mismatch(self):
        bad = VWAPSnapshot("BTC_USDT", 60, self.start + timedelta(seconds=60),
                           self.end + timedelta(seconds=60), 12, 102, 3)
        with self.assertRaises(ValueError):
            DataIntelligenceFeatureAdapter().build(self.item(vwap=bad))


if __name__ == "__main__":
    unittest.main()
