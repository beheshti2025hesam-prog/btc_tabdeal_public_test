import unittest
from datetime import datetime, timedelta, timezone

from core.data_engine.candles import Candle
from core.data_engine.momentum import MomentumCalculator
from core.data_engine.structure import MarketStructureCalculator


class MomentumStructureTests(unittest.TestCase):
    def candles(self):
        base = datetime(2026, 9, 24, tzinfo=timezone.utc)
        closes = [100, 101, 102, 104, 106, 108]
        return [
            Candle("BTC_USDT", 900, base + timedelta(minutes=i),
                   base + timedelta(minutes=i+15), c, c, c, c, 1, 1)
            for i, c in enumerate(closes)
        ]

    def test_momentum(self):
        result = MomentumCalculator(lookback=3).calculate(self.candles())[0]
        self.assertEqual(result.positive_candles, 3)
        self.assertGreater(result.momentum_return, 0)

    def test_structure(self):
        result = MarketStructureCalculator().calculate(self.candles())[0]
        self.assertEqual(result.structure, "higher_high_higher_low")
        self.assertEqual(result.swing_high, 108)
        self.assertEqual(result.swing_low, 100)


if __name__ == "__main__":
    unittest.main()
