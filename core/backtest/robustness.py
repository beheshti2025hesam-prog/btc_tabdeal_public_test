"""Execution-free stability measurements for OOS walk-forward folds.

This module summarizes dispersion across already validated OOS folds.
It does not tune parameters, alter observations, execute orders, mutate
capital, or make promotion decisions.
"""

from dataclasses import dataclass
import math

from core.backtest.walk_forward import WalkForwardResult


@dataclass(frozen=True)
class OOSStabilityResult:
    fold_count: int
    mean_win_rate: float
    min_win_rate: float
    max_win_rate: float
    win_rate_range: float
    mean_return: float
    min_return: float
    max_return: float
    return_range: float
    positive_return_folds: int
    negative_return_folds: int
    flat_return_folds: int


class OOSStabilityMeasurement:
    """Measure fold-to-fold stability without changing the OOS evaluation."""

    def run(self, result: WalkForwardResult) -> OOSStabilityResult:
        folds = result.folds
        if not folds:
            raise ValueError("walk-forward result must contain at least one fold")

        win_rates = [fold.result.win_rate for fold in folds]
        returns = [fold.result.total_return for fold in folds]

        if not all(math.isfinite(value) for value in (*win_rates, *returns)):
            raise ValueError("fold metrics must be finite")

        min_win_rate = min(win_rates)
        max_win_rate = max(win_rates)
        min_return = min(returns)
        max_return = max(returns)

        positive = sum(value > 0 for value in returns)
        negative = sum(value < 0 for value in returns)
        flat = len(returns) - positive - negative

        return OOSStabilityResult(
            fold_count=len(folds),
            mean_win_rate=sum(win_rates) / len(win_rates),
            min_win_rate=min_win_rate,
            max_win_rate=max_win_rate,
            win_rate_range=max_win_rate - min_win_rate,
            mean_return=sum(returns) / len(returns),
            min_return=min_return,
            max_return=max_return,
            return_range=max_return - min_return,
            positive_return_folds=positive,
            negative_return_folds=negative,
            flat_return_folds=flat,
        )
