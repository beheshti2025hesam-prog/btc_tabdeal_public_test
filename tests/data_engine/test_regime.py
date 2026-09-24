import unittest
from datetime import datetime, timezone
from core.data_engine.candles import Candle
from core.data_engine.regime import MarketRegimeClassifier

def candle(minute, o, c):
    start=datetime(2026,9,24,0,minute,tzinfo=timezone.utc)
    return Candle("BTC_USDT",60,start,start,o,max(o,c),min(o,c),c,1.0,1)

class MarketRegimeTests(unittest.TestCase):
    def test_classifies_uptrend(self):
        result=MarketRegimeClassifier(trend_threshold=0.01).classify([
            candle(0,100,101),candle(1,101,103),candle(2,103,105)
        ])[0]
        self.assertEqual(result.label,"uptrend")

    def test_classifies_range(self):
        result=MarketRegimeClassifier(trend_threshold=0.01).classify([
            candle(0,100,100.2),candle(1,100.2,99.9),candle(2,99.9,100.3)
        ])[0]
        self.assertEqual(result.label,"range")

    def test_insufficient_data(self):
        result=MarketRegimeClassifier(min_candles=3).classify([
            candle(0,100,101),candle(1,101,102)
        ])[0]
        self.assertEqual(result.label,"insufficient_data")

if __name__=="__main__":
    unittest.main()
