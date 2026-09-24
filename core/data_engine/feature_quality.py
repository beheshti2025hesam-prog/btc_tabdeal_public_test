"""Mother Agent - Feature Quality Gate v1.0

Deterministic safety gate between intelligence/features and downstream strategy.
It never creates, ranks, or recommends trades.
"""

from dataclasses import dataclass

from core.data_engine.feature_engine import FeatureSnapshot


@dataclass(frozen=True)
class FeatureQualityResult:
    passed: bool
    violations: tuple[str, ...]


class FeatureQualityGate:
    def __init__(self, require_ema: bool = True, require_vwap: bool = True):
        self.require_ema = require_ema
        self.require_vwap = require_vwap

    def evaluate(self, snapshot: FeatureSnapshot) -> FeatureQualityResult:
        violations: list[str] = []

        if not snapshot.symbol:
            violations.append("missing_symbol")
        if snapshot.timeframe_seconds <= 0:
            violations.append("invalid_timeframe")
        if snapshot.close is None or snapshot.close <= 0:
            violations.append("invalid_close")
        if self.require_ema and snapshot.ema is None:
            violations.append("missing_ema")
        if self.require_vwap and snapshot.vwap is None:
            violations.append("missing_vwap")

        if snapshot.buy_ratio is not None and not 0 <= snapshot.buy_ratio <= 1:
            violations.append("invalid_buy_ratio")
        if snapshot.volume_ratio is not None and snapshot.volume_ratio < 0:
            violations.append("invalid_volume_ratio")
        if snapshot.realized_volatility is not None and snapshot.realized_volatility < 0:
            violations.append("invalid_volatility")
        if snapshot.average_true_range is not None and snapshot.average_true_range < 0:
            violations.append("invalid_atr")

        return FeatureQualityResult(
            passed=not violations,
            violations=tuple(violations),
        )
