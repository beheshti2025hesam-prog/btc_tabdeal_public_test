"""Mother Agent - Risk Veto v1.0

Risk is a hard veto layer. It can block a strategy decision but never
creates a trade by itself.
"""

from dataclasses import dataclass

from core.data_engine.feature_engine import FeatureSnapshot
from core.strategy.baseline import Decision


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reasons: tuple[str, ...]


class RiskVeto:
    """Apply minimum deterministic safety constraints."""

    def __init__(
        self,
        *,
        max_realized_volatility: float | None = None,
        min_volume_ratio: float | None = None,
    ):
        self.max_realized_volatility = max_realized_volatility
        self.min_volume_ratio = min_volume_ratio

    def evaluate(
        self,
        snapshot: FeatureSnapshot,
        decision: Decision,
    ) -> RiskDecision:
        reasons: list[str] = []

        if decision == Decision.NO_TRADE:
            return RiskDecision(False, ("no_trade_decision",))

        if self.max_realized_volatility is not None:
            if snapshot.realized_volatility is None:
                reasons.append("volatility_missing")
            elif snapshot.realized_volatility > self.max_realized_volatility:
                reasons.append("volatility_above_limit")

        if self.min_volume_ratio is not None:
            if snapshot.volume_ratio is None:
                reasons.append("volume_ratio_missing")
            elif snapshot.volume_ratio < self.min_volume_ratio:
                reasons.append("volume_below_minimum")

        return RiskDecision(allowed=not reasons, reasons=tuple(reasons))
