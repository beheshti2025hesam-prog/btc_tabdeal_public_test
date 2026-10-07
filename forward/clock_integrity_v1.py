"""Fail-closed source/receive clock integrity guard."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass(frozen=True)
class ClockEvent:
    status: str
    reason: str | None = None
    age_seconds: float | None = None

class ForwardClockIntegrityV1:
    def __init__(self, *, max_clock_skew_seconds: float = 5.0):
        if max_clock_skew_seconds < 0:
            raise ValueError("max_clock_skew_seconds must be non-negative")
        self.max_skew = float(max_clock_skew_seconds)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)

    def validate(self, *, source_time: datetime, receive_time: datetime) -> ClockEvent:
        source = self._utc(source_time)
        receive = self._utc(receive_time)
        if source > receive:
            return ClockEvent("REJECT", "SOURCE_TIME_AFTER_RECEIVE_TIME")
        age = (receive - source).total_seconds()
        if age > self.max_skew:
            return ClockEvent("DRIFT", "SOURCE_RECEIVE_CLOCK_SKEW", age)
        return ClockEvent("OK", age_seconds=age)
