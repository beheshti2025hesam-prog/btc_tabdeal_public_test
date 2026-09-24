from core.backtest.walk_forward import WalkForwardSplitter


def test_walk_forward_windows_are_ordered_and_non_overlapping():
    values = tuple(range(10))
    windows = WalkForwardSplitter(train_size=4, test_size=2).split(values)

    assert [(w.train, w.test) for w in windows] == [
        ((0, 1, 2, 3), (4, 5)),
        ((2, 3, 4, 5), (6, 7)),
        ((4, 5, 6, 7), (8, 9)),
    ]
    for window in windows:
        assert max(window.train) < min(window.test)


def test_walk_forward_step_size_controls_expanding_start_without_shuffle():
    values = tuple(range(9))
    windows = WalkForwardSplitter(train_size=3, test_size=2, step_size=3).split(values)

    assert windows[0].train == (0, 1, 2)
    assert windows[0].test == (3, 4)
    assert windows[1].train == (3, 4, 5)
    assert windows[1].test == (6, 7)


def test_zero_step_size_is_rejected_instead_of_silently_defaulting():
    try:
        WalkForwardSplitter(train_size=2, test_size=1, step_size=0)
    except ValueError as exc:
        assert "step_size" in str(exc)
    else:
        raise AssertionError("step_size=0 must be rejected")


from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class TimedValue:
    timestamp: datetime
    value: int


def test_walk_forward_runner_passes_isolated_train_and_test_windows():
    values = tuple(
        TimedValue(datetime(2026, 1, 1, tzinfo=timezone.utc), i)
        for i in range(6)
    )
    seen = []

    def evaluator(train, test):
        seen.append((train, test))
        return sum(item.value for item in test)

    from core.backtest.walk_forward import WalkForwardRunner

    runs = WalkForwardRunner(
        WalkForwardSplitter(train_size=3, test_size=2, step_size=2)
    ).run(values, evaluator)

    assert len(runs) == 1
    assert seen[0][0] == values[:3]
    assert seen[0][1] == values[3:5]
    assert runs[0].result == 7
    assert runs[0].train_end < runs[0].test_start <= runs[0].test_end
