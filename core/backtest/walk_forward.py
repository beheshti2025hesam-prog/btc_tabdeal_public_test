"""Mother Agent - deterministic walk-forward split foundation v1.0."""

from dataclasses import dataclass
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
