"""Mother Agent - Feature Quality Gate v1.0

Deterministic safety gate between intelligence/features and downstream strategy.
It never creates, ranks, or recommends trades.
"""

from dataclasses import dataclass
import math

from core.data_engine.feature_engine import FeatureSnapshot


@dataclass(frozen=True)
class FeatureQualityResult:
    passed: bool
    violations: tuple[str, ...]


class FeatureQualityGate:
    def __init__(self, require_ema: bool = True, require_vwap: bool = True):
        self.require_ema = require_ema
        self.require_vwap = require_vwap

    @staticmethod
    def _is_positive_finite(value: float | None) -> bool:
        return value is not None and math.isfinite(value) and value > 0

    @staticmethod
    def _is_finite_non_negative(value: float | None) -> bool:
        return value is not None and math.isfinite(value) and value >= 0

    def evaluate(self, snapshot: FeatureSnapshot) -> FeatureQualityResult:
        violations: list[str] = []

        if not snapshot.symbol:
            violations.append("missing_symbol")
        if snapshot.timeframe_seconds <= 0:
            violations.append("invalid_timeframe")
        if snapshot.timestamp is not None and snapshot.timestamp.tzinfo is None:
            violations.append("invalid_timestamp")
        if not self._is_positive_finite(snapshot.close):
            violations.append("invalid_close")
        if self.require_ema:
            if snapshot.ema is None:
                violations.append("missing_ema")
            elif not self._is_positive_finite(snapshot.ema):
                violations.append("invalid_ema")
        if self.require_vwap:
            if snapshot.vwap is None:
                violations.append("missing_vwap")
            elif not self._is_positive_finite(snapshot.vwap):
                violations.append("invalid_vwap")

        if snapshot.buy_ratio is not None and (
            not math.isfinite(snapshot.buy_ratio)
            or not 0 <= snapshot.buy_ratio <= 1
        ):
            violations.append("invalid_buy_ratio")

        if snapshot.volume_ratio is not None and not self._is_finite_non_negative(snapshot.volume_ratio):
            violations.append("invalid_volume_ratio")
        if snapshot.realized_volatility is not None and not self._is_finite_non_negative(snapshot.realized_volatility):
            violations.append("invalid_volatility")
        if snapshot.average_true_range is not None and not self._is_finite_non_negative(snapshot.average_true_range):
            violations.append("invalid_atr")

        return FeatureQualityResult(
            passed=not violations,
            violations=tuple(violations),
        )
