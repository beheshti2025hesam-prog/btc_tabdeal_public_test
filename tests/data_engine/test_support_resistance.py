import unittest
from datetime import datetime, timedelta, timezone

from core.data_engine.candles import Candle
from core.data_engine.support_resistance import SupportResistanceCalculator


class SupportResistanceTests(unittest.TestCase):
    def test_detects_pivot_support_and_resistance(self):
        base = datetime(2026, 9, 24, tzinfo=timezone.utc)
        prices = [(99, 101), (98, 100), (99, 102), (100, 101), (97, 100)]
        candles = [
            Candle(
                "BTC_USDT", 60, base + timedelta(minutes=i),
                base + timedelta(minutes=i + 1),
                low, high, low, high, 1, 1
            )
            for i, (low, high) in enumerate(prices)
        ]
        levels = SupportResistanceCalculator().calculate(candles)
        self.assertTrue(any(level.kind == "support" and level.price == 98 for level in levels))
        self.assertTrue(any(level.kind == "resistance" and level.price == 102 for level in levels))


if __name__ == "__main__":
    unittest.main()
