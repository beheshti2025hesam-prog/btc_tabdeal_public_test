from core.evaluation.metrics import EvaluationMetricsCalculator
import math

import pytest


def test_drawdown_uses_starting_capital_as_equity_baseline():
    metrics = EvaluationMetricsCalculator().calculate(
        [100.0, -50.0, -100.0],
        starting_capital=1000.0,
    )

    assert metrics.net_pnl == -50.0
    assert metrics.max_drawdown == 150.0
    assert metrics.max_drawdown_pct == 15.0


def test_drawdown_does_not_treat_initial_capital_as_zero_peak():
    metrics = EvaluationMetricsCalculator().calculate(
        [-100.0],
        starting_capital=1000.0,
    )

    assert metrics.max_drawdown == 100.0
    assert metrics.max_drawdown_pct == 10.0


@pytest.mark.parametrize("invalid_pnl", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite_pnl(invalid_pnl):
    with pytest.raises(ValueError, match="finite"):
        EvaluationMetricsCalculator().calculate([1.0, invalid_pnl])
