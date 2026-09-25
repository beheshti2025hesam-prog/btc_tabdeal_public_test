import pytest

from core.evaluation.metrics import EvaluationMetrics
from core.experiments.contract import ExperimentSpec
from core.experiments.runner import ExperimentResult
from core.optimization.optimizer import GridSearchOptimizer
from core.optimization.promotion import PromotionGate, PromotionPolicy


def metrics(
    *,
    trades=40,
    win_rate=0.6,
    net_pnl=10.0,
    drawdown=5.0,
    expectancy=0.25,
):
    return EvaluationMetrics(
        trades=trades,
        wins=int(trades * win_rate),
        losses=trades - int(trades * win_rate),
        win_rate=win_rate,
        net_pnl=net_pnl,
        profit_factor=1.5,
        max_drawdown=drawdown,
        max_drawdown_pct=drawdown,
        expectancy=expectancy,
    )


def spec(name, risk):
    return ExperimentSpec(
        name=name,
        version="1",
        dataset_id="dataset",
        strategy_id="baseline-v1",
        timeframe_seconds=900,
        parameters=(("risk", str(risk)),),
    )


def result_for(specification, result_metrics):
    return ExperimentResult(
        experiment_id=specification.experiment_id,
        runs=(),
        metrics=result_metrics,
    )


def test_promotion_gate_rejects_insufficient_sample_and_negative_result():
    gate = PromotionGate(
        PromotionPolicy(
            min_trades=30,
            min_win_rate=0.55,
            max_drawdown_pct=10.0,
            min_expectancy=0.1,
        )
    )
    decision = gate.evaluate(
        metrics(
            trades=10,
            win_rate=0.6,
            net_pnl=-1.0,
            drawdown=2.0,
            expectancy=-0.1,
        )
    )

    assert decision.promoted is False
    assert "min_trades" in decision.violations
    assert "min_expectancy" in decision.violations
    assert "positive_net_pnl" in decision.violations


def test_promotion_gate_accepts_explicitly_passing_metrics():
    gate = PromotionGate(
        PromotionPolicy(
            min_trades=30,
            min_win_rate=0.55,
            max_drawdown_pct=10.0,
            min_expectancy=0.1,
        )
    )

    decision = gate.evaluate(metrics())

    assert decision.promoted is True
    assert decision.status == "PROMOTE"


def test_optimizer_orders_candidates_deterministically():
    evaluations = {
        "a": metrics(net_pnl=3.0),
        "b": metrics(net_pnl=9.0),
        "c": metrics(net_pnl=5.0),
    }

    def evaluate(specification):
        return result_for(specification, evaluations[specification.name])

    optimizer = GridSearchOptimizer(evaluate, objective="net_pnl")
    result = optimizer.evaluate(
        [spec("a", 0.01), spec("b", 0.02), spec("c", 0.03)]
    )

    assert [candidate.spec.name for candidate in result.candidates] == [
        "b",
        "c",
        "a",
    ]


def test_optimizer_can_filter_candidates_through_promotion_gate():
    evaluations = {
        "a": metrics(net_pnl=-1.0),
        "b": metrics(net_pnl=9.0),
    }

    def evaluate(specification):
        return result_for(specification, evaluations[specification.name])

    optimizer = GridSearchOptimizer(
        evaluate,
        objective="net_pnl",
        promotion_gate=PromotionGate(
            PromotionPolicy(min_trades=30, min_win_rate=0.55)
        ),
    )
    result = optimizer.evaluate(
        [spec("a", 0.01), spec("b", 0.02)]
    )

    assert [candidate.spec.name for candidate in result.candidates] == ["b"]
    assert [candidate.spec.name for candidate in result.rejected] == ["a"]


def test_optimizer_rejects_unknown_objective():
    optimizer = GridSearchOptimizer(
        lambda specification: result_for(specification, metrics()),
        objective="not_a_metric",
    )

    with pytest.raises(ValueError, match="unknown optimization objective"):
        optimizer.evaluate([spec("a", 0.01)])


def test_promotion_policy_rejects_non_finite_expectancy():
    with pytest.raises(ValueError, match="finite"):
        PromotionPolicy(min_expectancy=float("inf"))
