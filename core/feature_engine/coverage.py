"""HES Trade Agent - explicit coverage-gap evidence contract v1.

Descriptive evidence only; no signal generation or execution.
"""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class CoverageGap:
    """Explicit evidence that a symbol has an uncovered UTC interval."""

    symbol: str
    start: datetime
    end: datetime
    reason: str

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must be non-empty")
        if self.start.tzinfo is None or self.start.utcoffset() is None:
            raise ValueError("start must be timezone-aware")
        if self.end.tzinfo is None or self.end.utcoffset() is None:
            raise ValueError("end must be timezone-aware")
        if self.end.astimezone(timezone.utc) <= self.start.astimezone(timezone.utc):
            raise ValueError("gap end must be after start")
        if not self.reason:
            raise ValueError("reason must be non-empty")

    def overlaps(self, *, symbol: str, start: datetime, end: datetime) -> bool:
        """Return whether this gap overlaps the supplied UTC window."""
        if symbol != self.symbol:
            return False
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("start must be timezone-aware")
        if end.tzinfo is None or end.utcoffset() is None:
            raise ValueError("end must be timezone-aware")
        gap_start = self.start.astimezone(timezone.utc)
        gap_end = self.end.astimezone(timezone.utc)
        window_start = start.astimezone(timezone.utc)
        window_end = end.astimezone(timezone.utc)
        return gap_start < window_end and window_start < gap_end
