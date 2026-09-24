from core.evaluation.metrics import EvaluationMetricsCalculator


def test_drawdown_uses_starting_capital_as_equity_baseline():
    metrics = EvaluationMetricsCalculator().calculate(
        [100.0, -50.0, -100.0],
        starting_capital=1000.0,
    )

    assert metrics.net_pnl ==  -50.0
    assert metrics.max_drawdown == 150.0
    assert metrics.max_drawdown_pct == 15.0


def test_drawdown_does_not_treat_initial_capital_as_zero_peak():
    metrics = EvaluationMetricsCalculator().calculate(
        [-100.0],
        starting_capital=1000.0,
    )

    assert metrics.max_drawdown == 100.0
    assert metrics.max_drawdown_pct == 10.0
