import unittest

from core.data_engine.feature_engine import FeatureEngine
from core.data_engine.ema import EMAValue
from core.data_engine.vwap import VWAPSnapshot
from core.data_engine.pressure import BuySellPressure
from core.strategy.baseline import Decision
from core.strategy.confirmation import ConfirmationEngine
from core.strategy.decision import StrategyDecisionEngine
from core.strategy.risk import RiskVeto


class StrategyDecisionTests(unittest.TestCase):
    def snapshot(self, close, ema, vwap, buy_ratio, volatility=0.01):
        return FeatureEngine().build(
            symbol="BTC_USDT",
            timeframe_seconds=900,
            close=close,
            ema=EMAValue("BTC_USDT", 900, 20, None, ema),
            vwap=VWAPSnapshot("BTC_USDT", 100, vwap, 2),
            pressure=BuySellPressure(
                "BTC_USDT", buy_ratio * 100, (1 - buy_ratio) * 100,
                100, buy_ratio * 100 - (1 - buy_ratio) * 100,
                buy_ratio, 1 - buy_ratio, 1, 1,
            ),
        )

    def test_confirmation_requires_alignment(self):
        result = ConfirmationEngine().evaluate(
            self.snapshot(105, 100, 102, 0.6)
        )
        self.assertTrue(result.confirmed)

    def test_failed_confirmation_becomes_no_trade(self):
        result = StrategyDecisionEngine().evaluate(
            self.snapshot(105, 100, 108, 0.6)
        )
        self.assertEqual(result.decision, Decision.NO_TRADE)

    def test_risk_veto_blocks_decision(self):
        snapshot = self.snapshot(105, 100, 102, 0.6)
        result = StrategyDecisionEngine(
            risk_veto=RiskVeto(max_realized_volatility=0.001)
        ).evaluate(snapshot)
        self.assertEqual(result.decision, Decision.LONG)


if __name__ == "__main__":
    unittest.main()
