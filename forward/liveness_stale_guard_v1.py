"""Fail-closed liveness and stale-data guard for forward observations."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass(frozen=True)
class LivenessEvent:
    status: str
    reason: str | None = None

class ForwardLivenessGuardV1:
    def __init__(self, *, max_staleness_seconds: float = 30.0):
        if max_staleness_seconds <= 0:
            raise ValueError("max_staleness_seconds must be positive")
        self.max_staleness = timedelta(seconds=float(max_staleness_seconds))
        self.last_observed_at: datetime | None = None

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)

    def observe(self, observed_at: datetime, *, now: datetime) -> LivenessEvent:
        observed_at = self._utc(observed_at)
        now = self._utc(now)
        if observed_at > now:
            return LivenessEvent("REJECT", "FUTURE_OBSERVATION")
        self.last_observed_at = observed_at
        if now - observed_at > self.max_staleness:
            return LivenessEvent("STALE", "STALE_SOURCE_DATA")
        return LivenessEvent("LIVE")

    def heartbeat(self, *, now: datetime) -> LivenessEvent:
        now = self._utc(now)
        if self.last_observed_at is None:
            return LivenessEvent("NO_DATA", "NO_OBSERVATION_YET")
        if now - self.last_observed_at > self.max_staleness:
            return LivenessEvent("STALE", "STALE_SOURCE_DATA")
        return LivenessEvent("LIVE")
