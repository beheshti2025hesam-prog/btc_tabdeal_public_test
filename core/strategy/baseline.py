"""Mother Agent - Baseline Strategy v1.0

A deliberately conservative, deterministic decision layer.
No order execution and no exchange-specific behavior live here.
"""

from dataclasses import dataclass
from enum import Enum

from core.data_engine.feature_engine import FeatureSnapshot
from core.data_engine.feature_quality import FeatureQualityGate


class Decision(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class StrategyDecision:
    decision: Decision
    reasons: tuple[str, ...]


class BaselineStrategy:
    """Require valid features and simple trend/pressure alignment."""

    def __init__(self, quality_gate: FeatureQualityGate | None = None):
        self.quality_gate = quality_gate or FeatureQualityGate()

    def evaluate(self, snapshot: FeatureSnapshot) -> StrategyDecision:
        quality = self.quality_gate.evaluate(snapshot)
        if not quality.passed:
            return StrategyDecision(
                Decision.NO_TRADE,
                ("quality_gate_rejected", *quality.violations),
            )

        bullish = (
            snapshot.close is not None
            and snapshot.ema is not None
            and snapshot.close > snapshot.ema
            and snapshot.buy_ratio is not None
            and snapshot.buy_ratio > 0.5
        )
        bearish = (
            snapshot.close is not None
            and snapshot.ema is not None
            and snapshot.close < snapshot.ema
            and snapshot.buy_ratio is not None
            and snapshot.buy_ratio < 0.5
        )

        if bullish:
            return StrategyDecision(
                Decision.LONG,
                ("price_above_ema", "buy_pressure_dominant"),
            )
        if bearish:
            return StrategyDecision(
                Decision.SHORT,
                ("price_below_ema", "sell_pressure_dominant"),
            )

        return StrategyDecision(
            Decision.NO_TRADE,
            ("insufficient_alignment",),
        )
