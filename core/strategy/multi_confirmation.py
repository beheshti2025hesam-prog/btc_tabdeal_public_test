"""Mother Agent - generic multi-confirmation framework v1.0."""
from dataclasses import dataclass
from typing import Callable

from core.data_engine.feature_engine import FeatureSnapshot
from core.strategy.baseline import Decision


@dataclass(frozen=True)
class ConfirmationCheck:
    name: str
    passed: bool


@dataclass(frozen=True)
class MultiConfirmationResult:
    confirmed: bool
    passed_count: int
    required_count: int
    checks: tuple[ConfirmationCheck, ...]
    reasons: tuple[str, ...]


class MultiConfirmationEngine:
    """Evaluate independent confirmation rules without choosing a trade."""

    def __init__(self, checks: tuple[tuple[str, Callable[[FeatureSnapshot, Decision], bool]], ...],
                 required_count: int):
        if not checks:
            raise ValueError("checks must not be empty")
        if not 1 <= required_count <= len(checks):
            raise ValueError("required_count must be within check count")
        self.checks = checks
        self.required_count = required_count

    def evaluate(self, snapshot: FeatureSnapshot, decision: Decision) -> MultiConfirmationResult:
        if decision == Decision.NO_TRADE:
            return MultiConfirmationResult(False, 0, self.required_count, (), ("no_trade_decision",))
        results = tuple(
            ConfirmationCheck(name, bool(check(snapshot, decision)))
            for name, check in self.checks
        )
        passed = sum(check.passed for check in results)
        reasons = tuple(
            f"confirmation_pass:{check.name}" if check.passed else f"confirmation_fail:{check.name}"
            for check in results
        )
        return MultiConfirmationResult(
            passed >= self.required_count,
            passed,
            self.required_count,
            results,
            reasons,
        )
