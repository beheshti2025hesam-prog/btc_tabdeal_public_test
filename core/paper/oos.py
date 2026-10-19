"""Execution-free chronological paper OOS measurement."""
from dataclasses import dataclass
from typing import Iterable, Sequence

from core.backtest.validation import HistoricalObservation
from core.backtest.walk_forward import WalkForwardResult, WalkForwardValidation
from core.paper.robustness import PaperRobustnessResult, PaperRobustness
from core.paper.performance import PaperPerformanceResult, PaperPerformance


@dataclass(frozen=True)
class PaperOOSFold:
    train: tuple[HistoricalObservation, ...]
    test: tuple[HistoricalObservation, ...]
    performance: PaperPerformanceResult


@dataclass(frozen=True)
class PaperOOSResult:
    folds: tuple[PaperOOSFold, ...]
    robustness: PaperRobustnessResult


class PaperOOS:
    """Run canonical walk-forward folds and measure only unseen test portions."""

    def run(
        self,
        observations: Sequence[HistoricalObservation],
        validator: WalkForwardValidation,
    ) -> PaperOOSResult:
        result: WalkForwardResult = validator.run(observations)
        if not result.folds:
            raise ValueError("paper OOS requires at least one fold")

        paper_folds: list[PaperOOSFold] = []
        tests: list[Iterable[HistoricalObservation]] = []

        for fold in result.folds:
            test = tuple(fold.test)
            if not test:
                raise ValueError("paper OOS test folds must not be empty")
            performance = PaperPerformance().run(test)
            paper_folds.append(
                PaperOOSFold(
                    train=tuple(fold.train),
                    test=test,
                    performance=performance,
                )
            )
            tests.append(test)

        robustness = PaperRobustness().run(tests)
        return PaperOOSResult(tuple(paper_folds), robustness)
