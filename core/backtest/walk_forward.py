"""Mother Agent - deterministic walk-forward split foundation v1.0."""

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class WalkForwardWindow:
    train: tuple[T, ...]
    test: tuple[T, ...]


class WalkForwardSplitter:
    """Create ordered train/test windows without shuffling or look-ahead."""

    def __init__(self, *, train_size: int, test_size: int, step_size: int | None = None):
        if train_size <= 0 or test_size <= 0:
            raise ValueError("train_size and test_size must be positive")
        self.train_size = train_size
        self.test_size = test_size
        self.step_size = test_size if step_size is None else step_size
        if self.step_size <= 0:
            raise ValueError("step_size must be positive")

    def split(self, values: Sequence[T]) -> tuple[WalkForwardWindow, ...]:
        windows: list[WalkForwardWindow] = []
        start = 0
        while start + self.train_size + self.test_size <= len(values):
            train_end = start + self.train_size
            test_end = train_end + self.test_size
            windows.append(
                WalkForwardWindow(
                    train=tuple(values[start:train_end]),
                    test=tuple(values[train_end:test_end]),
                )
            )
            start += self.step_size
        return tuple(windows)


@dataclass(frozen=True)
class WalkForwardRun:
    """Research-only result for one walk-forward window."""
    index: int
    train_size: int
    test_size: int
    train_end: object
    test_start: object
    test_end: object
    result: object


class WalkForwardRunner:
    """Execute a supplied research evaluator on test windows only.

    The runner deliberately does not train, optimize, or execute orders. The
    evaluator receives an isolated train tuple and test tuple for each window,
    making it explicit where future-data leakage must not occur.
    """

    def __init__(self, splitter: WalkForwardSplitter):
        self.splitter = splitter

    def run(self, values: Sequence[T], evaluator) -> tuple[WalkForwardRun, ...]:
        windows = self.splitter.split(values)
        results: list[WalkForwardRun] = []
        for index, window in enumerate(windows):
            if not window.train or not window.test:
                continue
            train_end = self._timestamp_of(window.train[-1])
            test_start = self._timestamp_of(window.test[0])
            test_end = self._timestamp_of(window.test[-1])
            if train_end is not None and test_start is not None and test_start <= train_end:
                raise ValueError("walk-forward test data must start after training data")
            result = evaluator(window.train, window.test)
            results.append(
                WalkForwardRun(
                    index=index,
                    train_size=len(window.train),
                    test_size=len(window.test),
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    result=result,
                )
            )
        return tuple(results)

    @staticmethod
    def _timestamp_of(value):
        timestamp = getattr(value, "timestamp", None)
        return timestamp if isinstance(timestamp, datetime) else None
