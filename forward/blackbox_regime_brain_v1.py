"""Blackbox four-state regime policy; descriptive context never bypasses risk."""
from dataclasses import dataclass
from typing import Optional

ALLOWED_STATES = {"BULLISH", "BEARISH", "RANGE", "NO_TRADE"}
REGIME_MAP = {
    "UPTREND": "BULLISH", "BULLISH": "BULLISH",
    "DOWNTREND": "BEARISH", "BEARISH": "BEARISH",
    "RANGE": "RANGE",
    "TRANSITION": "NO_TRADE", "TRANSITION_UNCERTAIN": "NO_TRADE",
    "UNKNOWN": "NO_TRADE", "": "NO_TRADE", None: "NO_TRADE",
}

@dataclass(frozen=True)
class RegimeDecision:
    state: str
    actionable: bool
    reason: str
    source_regimes: tuple[str, ...]


def classify_regime(*, regimes: tuple[Optional[str], ...], data_fresh: bool,
                    data_complete: bool, confidence: float,
                    minimum_confidence: float = 0.70) -> RegimeDecision:
    """Conservative consensus across 15m/1h/4h; uncertainty => NO_TRADE.

    RANGE is a first-class state, never collapsed into trend or NO_TRADE.
    Mixed or transitional timeframes do not get majority-voted into a trade.
    """
    if not data_fresh:
        return RegimeDecision("NO_TRADE", False, "STALE_MARKET_DATA", tuple(str(x) for x in regimes))
    if not data_complete:
        return RegimeDecision("NO_TRADE", False, "INCOMPLETE_MARKET_DATA", tuple(str(x) for x in regimes))
    if len(regimes) != 3:
        return RegimeDecision("NO_TRADE", False, "REQUIRES_15M_1H_4H_CONTEXT", tuple(str(x) for x in regimes))
    normalized = tuple(REGIME_MAP.get(x, "NO_TRADE") for x in regimes)
    if "NO_TRADE" in normalized:
        return RegimeDecision("NO_TRADE", False, "TRANSITION_OR_UNKNOWN_REGIME", tuple(str(x) for x in regimes))
    if len(set(normalized)) != 1:
        return RegimeDecision("NO_TRADE", False, "MULTI_TIMEFRAME_REGIME_CONFLICT", tuple(str(x) for x in regimes))
    if not 0.0 <= confidence <= 1.0 or confidence < minimum_confidence:
        return RegimeDecision("NO_TRADE", False, "REGIME_CONFIDENCE_BELOW_FLOOR", tuple(str(x) for x in regimes))
    state = normalized[0]
    return RegimeDecision(state, True, f"CONFIRMED_{state}_REGIME", tuple(str(x) for x in regimes))
