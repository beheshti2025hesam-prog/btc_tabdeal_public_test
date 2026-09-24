"""Mother Agent - versioned feature value contract v1.1."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class FeatureValue:
    name: str
    timestamp: datetime
    value: Optional[float]
    timeframe_seconds: Optional[int] = None
    source: str = "derived"

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.timeframe_seconds is not None and self.timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        if not self.source.strip():
            raise ValueError("source must not be empty")
