import unittest

from core.evaluation.metrics import EvaluationMetricsCalculator


class EvaluationMetricsTests(unittest.TestCase):
    def test_metrics(self):
        result = EvaluationMetricsCalculator().calculate([10, -5, 15, -2])
        self.assertEqual(result.trades, 4)
        self.assertEqual(result.wins, 2)
        self.assertEqual(result.losses, 2)
        self.assertAlmostEqual(result.win_rate, 0.5)
        self.assertAlmostEqual(result.net_pnl, 18)
        self.assertAlmostEqual(result.profit_factor, 25 / 7)
        self.assertAlmostEqual(result.max_drawdown, 5)

    def test_empty_series(self):
        result = EvaluationMetricsCalculator().calculate([])
        self.assertEqual(result.trades, 0)
        self.assertEqual(result.win_rate, 0.0)
        self.assertEqual(result.max_drawdown, 0.0)


if __name__ == "__main__":
    unittest.main()
