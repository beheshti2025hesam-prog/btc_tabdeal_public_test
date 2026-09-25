"""Baseline strategy safety and determinism tests."""
import unittest

from core.feature_engine.quality import FeatureSnapshot
from core.strategy.baseline import BaselineDecision, BaselineStrategy, BaselineStrategyInput


class BaselineStrategyTests(unittest.TestCase):
    def _features(self, **overrides):
        values = dict(
            symbol="BTC_USDT", timeframe_seconds=900, close=110.0, ema=100.0,
            vwap=105.0, buy_ratio=0.8, realized_volatility=0.1,
            average_true_range=1.0, volume_ratio=1.0,
        )
        values.update(overrides)
        return FeatureSnapshot(**values)

    def test_long_requires_threshold_confirmations(self):
        strategy = BaselineStrategy(min_confirmations=3)
        data = BaselineStrategyInput(self._features(), trend="long")
        self.assertEqual(strategy.evaluate(data), BaselineDecision.LONG)

    def test_short_is_supported(self):
        features = self._features(close=90.0, ema=100.0, vwap=95.0, buy_ratio=0.2)
        data = BaselineStrategyInput(features, trend="short")
        self.assertEqual(BaselineStrategy().evaluate(data), BaselineDecision.SHORT)

    def test_conflict_returns_no_trade(self):
        features = self._features(close=110.0, ema=100.0, vwap=105.0, buy_ratio=0.8)
        data = BaselineStrategyInput(features, trend="short", structure_bias="short")
        self.assertEqual(BaselineStrategy().evaluate(data), BaselineDecision.NO_TRADE)

    def test_insufficient_confirmation_returns_no_trade(self):
        features = self._features(close=110.0, ema=100.0, vwap=105.0, buy_ratio=None)
        data = BaselineStrategyInput(features)
        self.assertEqual(BaselineStrategy().evaluate(data), BaselineDecision.NO_TRADE)

    def test_invalid_features_force_no_trade(self):
        features = self._features(close=float("nan"))
        self.assertEqual(
            BaselineStrategy().evaluate(BaselineStrategyInput(features)),
            BaselineDecision.NO_TRADE,
        )

    def test_invalid_bias_returns_no_trade(self):
        data = BaselineStrategyInput(self._features(), trend="up", structure_bias=None)
        self.assertEqual(BaselineStrategy().evaluate(data), BaselineDecision.NO_TRADE)

    def test_deterministic_result(self):
        data = BaselineStrategyInput(self._features(), trend="long", structure_bias="long")
        strategy = BaselineStrategy()
        self.assertEqual(strategy.evaluate(data), strategy.evaluate(data))


if __name__ == "__main__":
    unittest.main()
