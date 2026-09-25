"""Evaluation boundary tests."""
import unittest

from core.evaluation.boundary import evaluate_signals
from core.risk.boundary import RiskDecision
from core.strategy.baseline import BaselineDecision


class EvaluationBoundaryTests(unittest.TestCase):
    def test_counts_resolved_signals_and_vetoes(self):
        result = evaluate_signals([
            (BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, 1.0),
            (BaselineDecision.SHORT, RiskDecision.ALLOW_SIGNAL, -1.0),
            (BaselineDecision.LONG, RiskDecision.VETO, -1.0),
            (BaselineDecision.NO_TRADE, RiskDecision.VETO, 0.0),
        ])
        metrics = result.metrics
        self.assertEqual(metrics.total, 4)
        self.assertEqual(metrics.long_count, 2)
        self.assertEqual(metrics.short_count, 1)
        self.assertEqual(metrics.no_trade_count, 1)
        self.assertEqual(metrics.risk_veto_count, 2)
        self.assertEqual(metrics.win_count, 1)
        self.assertEqual(metrics.loss_count, 1)
        self.assertEqual(metrics.win_rate, 0.5)

    def test_zero_resolved_signals_has_zero_win_rate(self):
        result = evaluate_signals([
            (BaselineDecision.NO_TRADE, RiskDecision.VETO, 0.0),
        ])
        self.assertEqual(result.metrics.win_rate, 0.0)

    def test_non_finite_outcome_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_signals([(BaselineDecision.LONG, RiskDecision.ALLOW_SIGNAL, float("nan"))])


if __name__ == "__main__":
    unittest.main()
