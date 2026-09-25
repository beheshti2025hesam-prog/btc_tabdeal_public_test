"""Capital/risk boundary safety tests."""
import math
import unittest

from core.risk.boundary import RiskDecision, RiskInput, RiskPolicy
from core.strategy.baseline import BaselineDecision


class RiskBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.policy = RiskPolicy()

    def test_valid_signal_is_allowed_as_signal_only(self):
        result = self.policy.evaluate(RiskInput(BaselineDecision.LONG, 10000.0))
        self.assertEqual(result, RiskDecision.ALLOW_SIGNAL)

    def test_no_trade_is_vetoed(self):
        result = self.policy.evaluate(RiskInput(BaselineDecision.NO_TRADE, 10000.0))
        self.assertEqual(result, RiskDecision.VETO)

    def test_drawdown_limit_is_veto(self):
        result = self.policy.evaluate(
            RiskInput(BaselineDecision.LONG, 10000.0, current_drawdown_fraction=0.20)
        )
        self.assertEqual(result, RiskDecision.VETO)

    def test_invalid_equity_is_veto(self):
        result = self.policy.evaluate(RiskInput(BaselineDecision.SHORT, 0.0))
        self.assertEqual(result, RiskDecision.VETO)

    def test_nan_is_veto(self):
        result = self.policy.evaluate(
            RiskInput(BaselineDecision.LONG, math.nan)
        )
        self.assertEqual(result, RiskDecision.VETO)

    def test_leverage_above_one_is_veto(self):
        result = self.policy.evaluate(
            RiskInput(BaselineDecision.LONG, 10000.0, leverage=2.0)
        )
        self.assertEqual(result, RiskDecision.VETO)


if __name__ == "__main__":
    unittest.main()
