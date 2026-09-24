"""Mother Agent - Confirmation Engine v1.0

Combines independent descriptive features into an explicit confirmation result.
It does not execute orders.
"""

from dataclasses import dataclass

from core.data_engine.feature_engine import FeatureSnapshot


@dataclass(frozen=True)
class ConfirmationResult:
    confirmed: bool
    reasons: tuple[str, ...]


class ConfirmationEngine:
    """Conservative confirmation using trend, VWAP and pressure alignment."""

    def evaluate(self, snapshot: FeatureSnapshot) -> ConfirmationResult:
        reasons: list[str] = []

        if snapshot.close is None or snapshot.ema is None:
            reasons.append("missing_trend_reference")
        elif snapshot.close > snapshot.ema:
            reasons.append("price_above_ema")
        elif snapshot.close < snapshot.ema:
            reasons.append("price_below_ema")
        else:
            reasons.append("price_at_ema")

        if snapshot.close is None or snapshot.vwap is None:
            reasons.append("missing_vwap_reference")
        elif snapshot.close > snapshot.vwap:
            reasons.append("price_above_vwap")
        elif snapshot.close < snapshot.vwap:
            reasons.append("price_below_vwap")
        else:
            reasons.append("price_at_vwap")

        if snapshot.buy_ratio is None:
            reasons.append("missing_pressure")
        elif snapshot.buy_ratio > 0.5:
            reasons.append("buy_pressure_dominant")
        elif snapshot.buy_ratio < 0.5:
            reasons.append("sell_pressure_dominant")
        else:
            reasons.append("balanced_pressure")

        bullish = (
            snapshot.close is not None
            and snapshot.ema is not None
            and snapshot.vwap is not None
            and snapshot.buy_ratio is not None
            and snapshot.close > snapshot.ema
            and snapshot.close > snapshot.vwap
            and snapshot.buy_ratio > 0.5
        )
        bearish = (
            snapshot.close is not None
            and snapshot.ema is not None
            and snapshot.vwap is not None
            and snapshot.buy_ratio is not None
            and snapshot.close < snapshot.ema
            and snapshot.close < snapshot.vwap
            and snapshot.buy_ratio < 0.5
        )

        return ConfirmationResult(
            confirmed=bullish or bearish,
            reasons=tuple(reasons),
        )
