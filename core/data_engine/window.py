"""
HES Trade Agent - Windowed Data Intelligence contract.
Descriptive boundary only; no signals or execution.
"""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class IntelligenceWindow:
    """Canonical time window shared by Data Intelligence outputs."""
    symbol: str
    timeframe_seconds: int
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must be non-empty")
        if self.timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        if self.start.tzinfo is None or self.start.utcoffset() is None:
            raise ValueError("start must be timezone-aware")
        if self.end.tzinfo is None or self.end.utcoffset() is None:
            raise ValueError("end must be timezone-aware")
        start = self.start.astimezone(timezone.utc)
        end = self.end.astimezone(timezone.utc)
        if end <= start:
            raise ValueError("window end must be after start")
        if (end - start).total_seconds() != self.timeframe_seconds:
            raise ValueError("window duration must equal timeframe_seconds")


def validate_window_alignment(*, window, symbol, timeframe_seconds, start, end):
    """Reject outputs that cannot be joined to the canonical window."""
    if symbol != window.symbol:
        raise ValueError("symbol mismatch")
    if timeframe_seconds != window.timeframe_seconds:
        raise ValueError("timeframe mismatch")
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("start must be timezone-aware")
    if end.tzinfo is None or end.utcoffset() is None:
        raise ValueError("end must be timezone-aware")
    if start.astimezone(timezone.utc) != window.start.astimezone(timezone.utc):
        raise ValueError("window start mismatch")
    if end.astimezone(timezone.utc) != window.end.astimezone(timezone.utc):
        raise ValueError("window end mismatch")
