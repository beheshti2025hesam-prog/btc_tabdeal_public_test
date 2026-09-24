import pytest

from core.backtest.walk_forward import WalkForwardSplitter


def test_walk_forward_preserves_order_and_has_no_overlap():
    windows = WalkForwardSplitter(train_size=3, test_size=2).split(list(range(8)))
    assert windows[0].train == (0, 1, 2)
    assert windows[0].test == (3, 4)
    assert windows[1].train == (2, 3, 4)
    assert windows[1].test == (5, 6)


def test_custom_step_and_incomplete_tail_are_deterministic():
    windows = WalkForwardSplitter(train_size=2, test_size=2, step_size=3).split(list(range(7)))
    assert [(w.train, w.test) for w in windows] == [
        ((0, 1), (2, 3)),
        ((3, 4), (5, 6)),
    ]


def test_invalid_sizes_rejected():
    with pytest.raises(ValueError):
        WalkForwardSplitter(train_size=0, test_size=2)
