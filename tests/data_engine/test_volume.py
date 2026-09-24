import unittest

from core.data_engine.candles import Candle
from core.data_engine.volume import VolumeIntelligenceCalculator


class VolumeIntelligenceTests(unittest.TestCase):
    def candle(self, minute, volume):
        from datetime import datetime, timezone
        start = datetime(2026, 9, 24, 0, minute, tzinfo=timezone.utc)
        return Candle("BTC_USDT", 60, start, start, 100, 101, 99, 100, volume, 1)

    def test_snapshot_and_spike(self):
        result = VolumeIntelligenceCalculator(spike_multiplier=1.5).calculate([
            self.candle(0, 10), self.candle(1, 10), self.candle(2, 20)
        ])[0]
        self.assertEqual(result.candle_count, 3)
        self.assertEqual(result.total_volume, 40)
        self.assertAlmostEqual(result.average_volume, 40 / 3)
        self.assertAlmostEqual(result.latest_vs_average, 1.5)
        self.assertTrue(result.is_volume_spike)


if __name__ == "__main__":
    unittest.main()
