import unittest
from datetime import datetime, timezone
from core.data_engine.candles import Candle
from core.data_engine.momentum import MomentumCalculator

def candle(minute, close):
    start=datetime(2026,9,24,0,minute,tzinfo=timezone.utc)
    return Candle("BTC_USDT",60,start,start,close,close,close,close,1.0,1)

class MomentumTests(unittest.TestCase):
    def test_momentum_is_compounded_from_selected_returns(self):
        result=MomentumCalculator(lookback=2).calculate([
            candle(0,100), candle(1,110), candle(2,121)
        ])[0]
        self.assertAlmostEqual(result.momentum_return,0.21)

    def test_zero_previous_close_does_not_break_window_geometry(self):
        result=MomentumCalculator(lookback=2).calculate([
            candle(0,100), candle(1,0), candle(2,110), candle(3,121)
        ])[0]
        self.assertAlmostEqual(result.latest_return,0.10)
        self.assertAlmostEqual(result.momentum_return,0.10)
        self.assertEqual(result.positive_candles,1)

if __name__=="__main__":
    unittest.main()
