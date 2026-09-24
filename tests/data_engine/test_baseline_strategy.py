import unittest

from core.data_engine.feature_engine import FeatureEngine
from core.data_engine.ema import EMAValue
from core.data_engine.vwap import VWAPSnapshot
from core.data_engine.pressure import BuySellPressure
from core.strategy.baseline import BaselineStrategy, Decision


class BaselineStrategyTests(unittest.TestCase):
    def setUp(self):
        self.engine = FeatureEngine()
        self.strategy = BaselineStrategy()

    def snapshot(self, close, ema, buy_ratio):
        return self.engine.build(
            symbol="BTC_USDT",
            timeframe_seconds=900,
            close=close,
            ema=EMAValue("BTC_USDT", 900, 20, None, ema),
            vwap=VWAPSnapshot("BTC_USDT", 100, ema, 2),
            pressure=BuySellPressure(
                "BTC_USDT", buy_ratio * 100, (1 - buy_ratio) * 100,
                100, buy_ratio * 100 - (1 - buy_ratio) * 100,
                buy_ratio, 1 - buy_ratio, 1, 1,
            ),
        )

    def test_bullish_alignment_is_long(self):
        self.assertEqual(self.strategy.evaluate(self.snapshot(105, 100, .6)).decision, Decision.LONG)

    def test_bearish_alignment_is_short(self):
        self.assertEqual(self.strategy.evaluate(self.snapshot(95, 100, .4)).decision, Decision.SHORT)

    def test_neutral_alignment_is_no_trade(self):
        self.assertEqual(self.strategy.evaluate(self.snapshot(100, 100, .5)).decision, Decision.NO_TRADE)

    def test_quality_failure_is_no_trade(self):
        snapshot = self.engine.build(symbol="BTC_USDT", timeframe_seconds=900, close=100)
        result = self.strategy.evaluate(snapshot)
        self.assertEqual(result.decision, Decision.NO_TRADE)


if __name__ == "__main__":
    unittest.main()
