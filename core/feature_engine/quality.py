"""HES Trade Agent - deterministic Feature Quality Gate v1.0.

Safety boundary between descriptive features and downstream strategy.
This layer validates feature integrity only; it never creates or ranks trades.
"""
from dataclasses import dataclass
from datetime import datetime
import math


@dataclass(frozen=True)
class FeatureSnapshot:
    symbol: str
    timeframe_seconds: int
    close: float | None
    ema: float | None = None
    vwap: float | None = None
    buy_sell_delta: float | None = None
    buy_ratio: float | None = None
    realized_volatility: float | None = None
    average_true_range: float | None = None
    volume_ratio: float | None = None
    volume_spike: bool | None = None
    regime: str | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True)
class FeatureQualityResult:
    passed: bool
    violations: tuple[str, ...]


class FeatureQualityGate:
    """Validate feature snapshots at the downstream safety boundary."""

    def __init__(self, require_ema: bool = True, require_vwap: bool = True):
        self.require_ema = require_ema
        self.require_vwap = require_vwap

    @staticmethod
    def _positive_finite(value: float | None) -> bool:
        return value is not None and math.isfinite(value) and value > 0

    @staticmethod
    def _finite_non_negative(value: float | None) -> bool:
        return value is not None and math.isfinite(value) and value >= 0

    def evaluate(self, snapshot: FeatureSnapshot) -> FeatureQualityResult:
        violations: list[str] = []

        if not snapshot.symbol:
            violations.append("missing_symbol")
        if snapshot.timeframe_seconds <= 0:
            violations.append("invalid_timeframe")

        if snapshot.timestamp is not None:
            if snapshot.timestamp.tzinfo is None or snapshot.timestamp.utcoffset() is None:
                violations.append("invalid_timestamp")

        if not self._positive_finite(snapshot.close):
            violations.append("invalid_close")

        if self.require_ema:
            if snapshot.ema is None:
                violations.append("missing_ema")
            elif not self._positive_finite(snapshot.ema):
                violations.append("invalid_ema")

        if self.require_vwap:
            if snapshot.vwap is None:
                violations.append("missing_vwap")
            elif not self._positive_finite(snapshot.vwap):
                violations.append("invalid_vwap")

        if snapshot.buy_sell_delta is not None and not math.isfinite(snapshot.buy_sell_delta):
            violations.append("invalid_buy_sell_delta")

        if snapshot.buy_ratio is not None and (
            not math.isfinite(snapshot.buy_ratio)
            or not 0 <= snapshot.buy_ratio <= 1
        ):
            violations.append("invalid_buy_ratio")

        if snapshot.volume_ratio is not None and not self._finite_non_negative(snapshot.volume_ratio):
            violations.append("invalid_volume_ratio")
        if snapshot.realized_volatility is not None and not self._finite_non_negative(snapshot.realized_volatility):
            violations.append("invalid_volatility")
        if snapshot.average_true_range is not None and not self._finite_non_negative(snapshot.average_true_range):
            violations.append("invalid_atr")

        return FeatureQualityResult(not violations, tuple(violations))
