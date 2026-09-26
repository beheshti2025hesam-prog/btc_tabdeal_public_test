"""HES Trade Agent - Feature coverage evidence boundary v1.

Explicit evidence contract for known data-coverage gaps. A sequence gap alone
is not treated as a coverage gap; callers must provide an explicit UTC interval.
"""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class CoverageGap:
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
        if self.end <= self.start:
            raise ValueError("coverage gap end must be after start")
        if not self.reason:
            raise ValueError("coverage gap reason must be non-empty")

    def overlaps(self, *, symbol: str, start: datetime, end: datetime) -> bool:
        if symbol != self.symbol:
            return False
        gap_start = self.start.astimezone(timezone.utc)
        gap_end = self.end.astimezone(timezone.utc)
        window_start = start.astimezone(timezone.utc)
        window_end = end.astimezone(timezone.utc)
        return gap_start < window_end and window_start < gap_end
