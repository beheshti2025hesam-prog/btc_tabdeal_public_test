"""Execution-free robustness measurement for paper performance."""
from dataclasses import dataclass
import math
from typing import Iterable

from core.backtest.validation import HistoricalObservation
from core.paper.performance import PaperPerformance
from core.paper.session import PaperState


@dataclass(frozen=True)
class PaperRobustnessResult:
    fold_count: int
    mean_win_rate: float
    min_win_rate: float
    max_win_rate: float
    win_rate_range: float
    mean_return: float
    min_return: float
    max_return: float
    return_range: float
    positive_folds: int
    negative_folds: int
    flat_folds: int


class PaperRobustness:
    """Measure paper performance stability across independent chronological folds."""

    def run(
        self,
        folds: Iterable[Iterable[HistoricalObservation]],
    ) -> PaperRobustnessResult:
        results = [PaperPerformance().run(fold) for fold in folds]
        if not results:
            raise ValueError("paper robustness requires at least one fold")

        for result in results:
            metrics = (result.win_rate, result.total_return, result.max_drawdown)
            if not all(math.isfinite(value) for value in metrics):
                raise ValueError("paper robustness metrics must be finite")
            if result.open_state is not PaperState.FLAT:
                raise ValueError("paper robustness requires closed paper folds")

        win_rates = [result.win_rate for result in results]
        returns = [result.total_return for result in results]
        positive = sum(value > 0 for value in returns)
        negative = sum(value < 0 for value in returns)

        return PaperRobustnessResult(
            fold_count=len(results),
            mean_win_rate=sum(win_rates) / len(win_rates),
            min_win_rate=min(win_rates),
            max_win_rate=max(win_rates),
            win_rate_range=max(win_rates) - min(win_rates),
            mean_return=sum(returns) / len(returns),
            min_return=min(returns),
            max_return=max(returns),
            return_range=max(returns) - min(returns),
            positive_folds=positive,
            negative_folds=negative,
            flat_folds=len(returns) - positive - negative,
        )
