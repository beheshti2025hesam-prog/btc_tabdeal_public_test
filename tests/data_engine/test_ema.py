import unittest
from datetime import datetime, timezone

from core.data_engine.candles import Candle
from core.data_engine.ema import EMACalculator


class EMATests(unittest.TestCase):
    def test_ema_series(self):
        start = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)
        candles = [
            Candle("BTC_USDT", 60, start, start, 0, 0, 0, 10, 1, 1),
            Candle("BTC_USDT", 60, start, start, 0, 0, 0, 12, 1, 1),
            Candle("BTC_USDT", 60, start, start, 0, 0, 0, 14, 1, 1),
        ]
        result = EMACalculator(period=2).calculate(candles)
        self.assertEqual(len(result), 3)
        self.assertAlmostEqual(result[0].value, 10)
        self.assertAlmostEqual(result[1].value, 11.3333333333)
        self.assertAlmostEqual(result[2].value, 13.1111111111)


if __name__ == "__main__":
    unittest.main()
