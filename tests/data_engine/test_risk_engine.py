import unittest

from core.risk.engine import CapitalRiskEngine, RiskConfig


class CapitalRiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = CapitalRiskEngine(
            RiskConfig(account_equity=10000, risk_per_trade=0.01, max_leverage=10)
        )

    def test_valid_three_to_one_trade_is_allowed(self):
        result = self.engine.assess(
            entry_price=100, stop_price=99, target_price=103
        )
        self.assertTrue(result.allowed)
        self.assertAlmostEqual(result.position_size, 100.0)

    def test_low_rr_is_rejected(self):
        result = self.engine.assess(
            entry_price=100, stop_price=99, target_price=101
        )
        self.assertFalse(result.allowed)
        self.assertIn("reward_risk_below_minimum", result.reasons)

    def test_zero_stop_is_rejected(self):
        result = self.engine.assess(
            entry_price=100, stop_price=100, target_price=103
        )
        self.assertFalse(result.allowed)
        self.assertIn("zero_stop_distance", result.reasons)

    def test_leverage_cap_is_enforced(self):
        result = CapitalRiskEngine(
            RiskConfig(account_equity=1000, risk_per_trade=0.1, max_leverage=2)
        ).assess(entry_price=100, stop_price=99, target_price=103)
        self.assertFalse(result.allowed)
        self.assertIn("leverage_limit", result.reasons)


if __name__ == "__main__":
    unittest.main()
