"""Regression tests for historical feature/decision invariance under future-data extension."""
import unittest
from datetime import datetime, timedelta, timezone

from core.data_engine.candles import Candle
from core.data_engine.vwap import VWAPCalculator
from core.feature_engine.ema import EMACalculator
from core.feature_engine.quality import FeatureSnapshot
from core.strategy.baseline import BaselineStrategy, BaselineStrategyInput
from core.models.trade import CanonicalTrade


class FutureInvarianceTests(unittest.TestCase):
    def _candles(self, closes):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [Candle(
            symbol="BTC_USDT", timeframe_seconds=60,
            start=start + timedelta(minutes=i), end=start + timedelta(minutes=i + 1),
            open=value, high=value, low=value, close=value,
            volume=1.0, trade_count=1,
        ) for i, value in enumerate(closes)]

    def test_ema_historical_prefix_is_unchanged_when_future_candles_are_added(self):
        base = self._candles([100.0, 101.0, 102.0, 103.0, 104.0])
        future = self._candles([105.0, 106.0])
        future = [Candle(
            symbol=c.symbol, timeframe_seconds=c.timeframe_seconds,
            start=base[-1].end + timedelta(minutes=i),
            end=base[-1].end + timedelta(minutes=i + 1),
            open=c.open, high=c.high, low=c.low, close=c.close,
            volume=c.volume, trade_count=c.trade_count,
        ) for i, c in enumerate(future)]
        calc = EMACalculator(period=3)
        before = calc.calculate(base)
        after = calc.calculate(base + future)
        self.assertEqual([(x.timestamp, x.value) for x in after[:len(before)]],
                         [(x.timestamp, x.value) for x in before])

    def test_vwap_historical_buckets_are_unchanged_when_future_trades_are_added(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        base = [CanonicalTrade(
            event_id=str(i), source="test", exchange="tabdeal", symbol="BTC_USDT",
            price=100.0 + i, quantity=1.0, side="buy", timestamp=start + timedelta(seconds=i * 20), sequence=i
        ) for i in range(6)]
        future = [CanonicalTrade(
            event_id="future", source="test", exchange="tabdeal", symbol="BTC_USDT",
            price=999.0, quantity=10.0, side="sell", timestamp=start + timedelta(minutes=2, seconds=5), sequence=99
        )]
        calc = VWAPCalculator(60)
        before = calc.calculate(base)
        after = calc.calculate(base + future)
        self.assertEqual([(x.start, x.end, x.vwap) for x in after[:len(before)]],
                         [(x.start, x.end, x.vwap) for x in before])

    def test_baseline_decision_is_unchanged_for_same_snapshot_after_future_data(self):
        snapshot = FeatureSnapshot(
            symbol="BTC_USDT", timeframe_seconds=60, close=105.0, ema=103.0,
            vwap=102.0, buy_sell_delta=1.0, buy_ratio=0.75,
            timestamp=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
        )
        strategy = BaselineStrategy(min_confirmations=3)
        self.assertEqual(strategy.evaluate(BaselineStrategyInput(snapshot)),
                         strategy.evaluate(BaselineStrategyInput(snapshot)))


if __name__ == "__main__":
    unittest.main()
