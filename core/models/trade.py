"""
Mother Agent - Canonical Trade Model
Data Contract v1.0
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class CanonicalTrade:
    """
    Canonical representation of a single trade event.

    This model is independent from any specific exchange,
    symbol, market, API, or data source.
    """

    event_id: str
    source: str
    exchange: str
    symbol: str

    price: float
    quantity: float
    side: str

    timestamp: datetime
    sequence: Optional[int] = None

    ingested_at: Optional[datetime] = None
