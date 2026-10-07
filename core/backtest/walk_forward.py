"""Deterministic out-of-sample / walk-forward validation boundary.

This module only partitions already validated historical observations into
strictly chronological train/test folds and evaluates each test window.
No fitting, execution, capital mutation, leverage, or live trading occurs.

The baseline strategy currently has no learned parameters, so the training
window is retained as a provenance boundary rather than used to tune the
baseline. Future learned models must fit exclusively on the training window
before evaluating the corresponding test window.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from core.backtest.engine import BacktestResult
from core.backtest.validation import HistoricalObservation, HistoricalValidation



@dataclass(frozen=True)
class WalkForwardConfig:
    """Backward-compatible configuration for the execution-free paper OOS API."""
    train_size: int
    test_size: int
    step_size: int | None = None
    embargo_size: int = 0

    def __post_init__(self) -> None:
        if self.train_size <= 0: raise ValueError("train_size must be positive")
        if self.test_size <= 0: raise ValueError("test_size must be positive")
        if self.step_size is not None and self.step_size < self.test_size: raise ValueError("step_size must be at least test_size")
        if self.embargo_size < 0: raise ValueError("embargo_size must not be negative")

@dataclass(frozen=True)
class WalkForwardWindow:
    train: tuple[HistoricalObservation, ...]
    test: tuple[HistoricalObservation, ...]

def walk_forward(observations: Iterable[HistoricalObservation], config: WalkForwardConfig) -> tuple[WalkForwardWindow, ...]:
    """Create strict chronological train/test windows without fitting or tuning."""
    rows = list(observations)
    HistoricalValidation().run(rows)
    step = config.step_size or config.test_size
    windows: list[WalkForwardWindow] = []
    start = 0
    while True:
        train_end = start + config.train_size
        test_start = train_end + config.embargo_size
        test_end = test_start + config.test_size
        if test_end > len(rows): break
        train = tuple(rows[start:train_end])
        test = tuple(rows[test_start:test_end])
        if train[-1].timestamp >= test[0].timestamp: raise ValueError("train/test windows overlap or are not chronological")
        if windows and windows[-1].test[-1].timestamp >= test[0].timestamp: raise ValueError("OOS test windows overlap")
        windows.append(WalkForwardWindow(train=train, test=test))
        start += step
    if not windows:
        required = config.train_size + config.embargo_size + config.test_size
        raise ValueError(f"insufficient observations for walk-forward validation: need at least {required}, got {len(rows)}")
    return tuple(windows)
@dataclass(frozen=True)
class WalkForwardFold:
    index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_observations: int
    test_observations: int
    result: BacktestResult


@dataclass(frozen=True)
class WalkForwardResult:
    folds: tuple[WalkForwardFold, ...]
    samples: int
    evaluated: int
    vetoed: int
    no_trade: int
    wins: int
    losses: int
    total_return: float
    win_rate: float


class WalkForwardValidation:
    """Run deterministic chronological OOS evaluation over historical rows."""

    def __init__(
        self,
        train_size: int,
        test_size: int,
        step_size: int | None = None,
        embargo_size: int = 0,
    ) -> None:
        if train_size <= 0:
            raise ValueError("train_size must be positive")
        if test_size <= 0:
            raise ValueError("test_size must be positive")
        if step_size is not None and step_size < test_size:
            raise ValueError("step_size must be at least test_size")
        if embargo_size < 0:
            raise ValueError("embargo_size must not be negative")
        self.train_size = train_size
        self.test_size = test_size
        self.step_size = step_size or test_size
        self.embargo_size = embargo_size

    def run(self, observations: Iterable[HistoricalObservation]) -> WalkForwardResult:
        rows = list(observations)
        HistoricalValidation().run(rows)

        folds: list[WalkForwardFold] = []
        start = 0
        fold_index = 0

        while True:
            train_end = start + self.train_size
            test_start = train_end + self.embargo_size
            test_end = test_start + self.test_size
            if test_end > len(rows):
                break

            train = rows[start:train_end]
            test = rows[test_start:test_end]

            if train[-1].timestamp >= test[0].timestamp:
                raise ValueError("train/test windows overlap or are not chronological")
            if folds and folds[-1].test_end >= test[0].timestamp:
                raise ValueError("OOS test windows overlap")

            result = HistoricalValidation().run(test)
            folds.append(
                WalkForwardFold(
                    index=fold_index,
                    train_start=train[0].timestamp,
                    train_end=train[-1].timestamp,
                    test_start=test[0].timestamp,
                    test_end=test[-1].timestamp,
                    train_observations=len(train),
                    test_observations=len(test),
                    result=result,
                )
            )

            fold_index += 1
            start += self.step_size

        if not folds:
            required = self.train_size + self.embargo_size + self.test_size
            raise ValueError(
                f"insufficient observations for walk-forward validation: "
                f"need at least {required}, got {len(rows)}"
            )

        samples = sum(f.result.samples for f in folds)
        evaluated = sum(f.result.evaluated for f in folds)
        vetoed = sum(f.result.vetoed for f in folds)
        no_trade = sum(f.result.no_trade for f in folds)
        wins = sum(f.result.wins for f in folds)
        losses = sum(f.result.losses for f in folds)
        total_return = sum(f.result.total_return for f in folds)
        resolved = wins + losses

        return WalkForwardResult(
            folds=tuple(folds),
            samples=samples,
            evaluated=evaluated,
            vetoed=vetoed,
            no_trade=no_trade,
            wins=wins,
            losses=losses,
            total_return=total_return,
            win_rate=wins / resolved if resolved else 0.0,
        )
