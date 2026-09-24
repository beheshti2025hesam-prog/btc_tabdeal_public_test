import pytest

from core.experiments.contract import ExperimentSpec


def test_experiment_id_is_deterministic_and_order_independent():
    left = ExperimentSpec(
        name="baseline",
        version="1",
        dataset_id="tabdeal-btc-2026-09",
        strategy_id="baseline-v1",
        timeframe_seconds=900,
        parameters=(("risk", "0.01"), ("confirmations", "5")),
    )
    right = ExperimentSpec(
        name="baseline",
        version="1",
        dataset_id="tabdeal-btc-2026-09",
        strategy_id="baseline-v1",
        timeframe_seconds=900,
        parameters=(("confirmations", "5"), ("risk", "0.01")),
    )

    assert left.experiment_id == right.experiment_id
    assert len(left.experiment_id) == 64


def test_experiment_rejects_duplicate_parameter_names():
    with pytest.raises(ValueError, match="unique"):
        ExperimentSpec(
            name="baseline",
            version="1",
            dataset_id="dataset",
            strategy_id="strategy",
            timeframe_seconds=900,
            parameters=(("risk", "0.01"), ("risk", "0.02")),
        )


def test_experiment_requires_positive_timeframe():
    with pytest.raises(ValueError, match="positive"):
        ExperimentSpec(
            name="baseline",
            version="1",
            dataset_id="dataset",
            strategy_id="strategy",
            timeframe_seconds=0,
        )
