import unittest
from datetime import datetime, timezone
from core.data_engine.candles import Candle
from core.data_engine.volatility import VolatilityCalculator

def candle(minute, o, h, l, c):
    start=datetime(2026,9,24,0,minute,tzinfo=timezone.utc)
    return Candle("BTC_USDT",60,start,start, o,h,l,c,1.0,1)

class VolatilityTests(unittest.TestCase):
    def test_calculates_returns_and_atr(self):
        result=VolatilityCalculator().calculate([
            candle(0,100,102,99,101),
            candle(1,101,104,100,103),
            candle(2,103,105,102,104),
        ])[0]
        self.assertEqual(result.candle_count,3)
        self.assertGreater(result.return_stddev,0)
        self.assertGreater(result.realized_volatility,0)
        self.assertAlmostEqual(result.average_true_range,(4+3)/2)

if __name__=="__main__":
    unittest.main()
