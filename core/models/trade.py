"""
HES Trade Agent - Canonical Trade Model.
Data Contract v1.0.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class CanonicalTrade:
    """Exchange-agnostic representation of one received trade event."""
    event_id: str
    source: str
    exchange: str
    symbol: str
    price: float
    quantity: float
    side: str
    timestamp: datetime
    # Opaque venue metadata; never assume it is an identity or ordering key.
    sequence: Optional[int | str] = None
    ingested_at: Optional[datetime] = None
