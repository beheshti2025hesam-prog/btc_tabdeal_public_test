import pytest

from core.evaluation.metrics import EvaluationMetricsCalculator


def test_drawdown_percentage_and_expectancy_are_deterministic():
    metrics = EvaluationMetricsCalculator().calculate(
        [10.0, -5.0, -20.0, 15.0],
        starting_capital=200.0,
    )
    assert metrics.max_drawdown == pytest.approx(25.0)
    assert metrics.max_drawdown_pct == pytest.approx(12.5)
    assert metrics.expectancy == pytest.approx(0.0)


def test_starting_capital_must_be_positive():
    with pytest.raises(ValueError, match="starting_capital"):
        EvaluationMetricsCalculator().calculate([1.0], starting_capital=0.0)
