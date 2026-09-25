import unittest
from datetime import datetime, timezone

from core.data_engine.candles import Candle, TradeCandleAggregator
from core.data_engine.ema import EMACalculator
from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.volatility import VolatilityCalculator
from core.data_engine.volume import VolumeIntelligenceCalculator
from core.data_engine.vwap import VWAPCalculator


class DataIntelligenceBoundaryTests(unittest.TestCase):
    def test_candle_aggregation_is_deterministic_for_equal_timestamps(self):
        normalizer = RawDataNormalizer()
        trades = [
            normalizer.normalize_row({
                "symbol": "BTC_USDT", "price": "101", "amount": "1",
                "side": "buy", "updated": "2026-09-24T00:00:01Z", "sequence": "2",
            }),
            normalizer.normalize_row({
                "symbol": "BTC_USDT", "price": "100", "amount": "1",
                "side": "buy", "updated": "2026-09-24T00:00:01Z", "sequence": "1",
            }),
        ]
        candle = TradeCandleAggregator(60).aggregate(trades)[0]
        self.assertEqual(candle.open, 100)
        self.assertEqual(candle.close, 101)

    def test_candle_timeframe_must_be_positive(self):
        with self.assertRaises(ValueError):
            TradeCandleAggregator(0)
        with self.assertRaises(ValueError):
            TradeCandleAggregator(-60)

    def test_ema_period_must_be_positive(self):
        with self.assertRaises(ValueError):
            EMACalculator(0)
        with self.assertRaises(ValueError):
            EMACalculator(-1)

    def test_volume_spike_multiplier_must_be_positive(self):
        with self.assertRaises(ValueError):
            VolumeIntelligenceCalculator(0)
        with self.assertRaises(ValueError):
            VolumeIntelligenceCalculator(-1)

    def test_volume_zero_average_is_safe(self):
        start = datetime(2026, 9, 24, tzinfo=timezone.utc)
        candle = Candle("BTC_USDT", 60, start, start, 100, 100, 100, 100, 0.0, 1)
        result = VolumeIntelligenceCalculator().calculate([candle])[0]
        self.assertEqual(result.average_volume, 0.0)
        self.assertEqual(result.latest_vs_average, 0.0)
        self.assertFalse(result.is_volume_spike)

    def test_vwap_zero_volume_is_safe(self):
        normalizer = RawDataNormalizer()
        trade = normalizer.normalize_row({
            "symbol": "BTC_USDT", "price": "100", "amount": "1",
            "side": "buy", "updated": "2026-09-24T00:00:01Z", "sequence": "1",
        })
        # Canonical trades require positive quantity, so zero-volume VWAP
        # is represented by an empty input rather than an invalid trade.
        self.assertEqual(VWAPCalculator().calculate([]), [])

    def test_volatility_empty_input_is_safe(self):
        self.assertEqual(VolatilityCalculator().calculate([]), [])


if __name__ == "__main__":
    unittest.main()
