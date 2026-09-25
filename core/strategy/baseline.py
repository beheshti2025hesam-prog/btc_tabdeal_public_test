"""Deterministic, signal-only baseline strategy contract.

This layer converts already-validated descriptive features into a bounded
decision. It never places orders, sizes positions, sets leverage, or manages
capital. Insufficient or conflicting evidence deterministically yields NO_TRADE.
"""
from dataclasses import dataclass
from enum import Enum
import math

from core.feature_engine.quality import FeatureQualityGate, FeatureSnapshot


class BaselineDecision(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class BaselineStrategyInput:
    features: FeatureSnapshot
    trend: str | None = None
    structure_bias: str | None = None


class BaselineStrategy:
    """Conservative confirmation-count baseline; signal-only by design."""

    def __init__(self, min_confirmations: int = 3):
        if min_confirmations <= 0:
            raise ValueError("min_confirmations must be positive")
        self.min_confirmations = min_confirmations
        self.quality_gate = FeatureQualityGate()

    def evaluate(self, data: BaselineStrategyInput) -> BaselineDecision:
        quality = self.quality_gate.evaluate(data.features)
        if not quality.passed:
            return BaselineDecision.NO_TRADE

        long_score = 0
        short_score = 0

        close = data.features.close
        ema = data.features.ema
        vwap = data.features.vwap
        buy_ratio = data.features.buy_ratio

        if close is None or ema is None or vwap is None:
            return BaselineDecision.NO_TRADE
        if not all(math.isfinite(x) for x in (close, ema, vwap)):
            return BaselineDecision.NO_TRADE

        if close > ema:
            long_score += 1
        elif close < ema:
            short_score += 1

        if close > vwap:
            long_score += 1
        elif close < vwap:
            short_score += 1

        if buy_ratio is not None:
            if buy_ratio > 0.5:
                long_score += 1
            elif buy_ratio < 0.5:
                short_score += 1

        for bias in (data.trend, data.structure_bias):
            if bias == "long":
                long_score += 1
            elif bias == "short":
                short_score += 1

        if long_score >= self.min_confirmations and long_score > short_score:
            return BaselineDecision.LONG
        if short_score >= self.min_confirmations and short_score > long_score:
            return BaselineDecision.SHORT
        return BaselineDecision.NO_TRADE
