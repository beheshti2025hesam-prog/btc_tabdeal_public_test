"""Mother Agent - Signal-Only / Assistive contract v1.1.

This layer can describe an actionable idea without placing an order.
Execution is intentionally absent from this contract.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SignalMode(str, Enum):
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    SIGNAL_ONLY = "SIGNAL_ONLY"
    ASSISTIVE = "ASSISTIVE"


class SignalIntent(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class SignalRecord:
    symbol: str
    timeframe_seconds: int
    timestamp: object
    mode: SignalMode
    intent: SignalIntent
    confidence: float | None
    reasons: tuple[str, ...]
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        if not isinstance(self.timestamp, datetime) or self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.intent == SignalIntent.NO_TRADE:
            if any(
                value is not None
                for value in (self.entry_price, self.stop_price, self.target_price)
            ):
                raise ValueError("NO_TRADE cannot contain trade prices")
        elif any(
            value is not None
            and value <= 0
            for value in (self.entry_price, self.stop_price, self.target_price)
        ):
            raise ValueError("trade prices must be positive")
