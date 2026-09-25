import pytest

from core.learning.outcomes import OutcomeLearner


def test_outcome_learner_accumulates_deterministically():
    learner = OutcomeLearner()
    learner.observe("baseline:BTC_USDT:900", 3.0)
    learner.observe("baseline:BTC_USDT:900", -1.0)
    learner.observe("baseline:BTC_USDT:900", 0.0)

    stats = learner.stats("baseline:BTC_USDT:900")
    assert stats.observations == 3
    assert stats.wins == 1
    assert stats.losses == 1
    assert stats.total_pnl == 2.0
    assert stats.win_rate == pytest.approx(1 / 3)
    assert stats.expectancy == pytest.approx(2 / 3)


def test_unknown_key_is_empty_and_snapshot_is_sorted():
    learner = OutcomeLearner()
    assert learner.stats("missing").observations == 0
    learner.observe("z", 1.0)
    learner.observe("a", 1.0)
    assert [item.key for item in learner.snapshot()] == ["a", "z"]


def test_outcome_learner_rejects_invalid_input():
    learner = OutcomeLearner()
    with pytest.raises(ValueError):
        learner.observe("", 1.0)
    with pytest.raises(ValueError):
        learner.observe("x", float("nan"))
