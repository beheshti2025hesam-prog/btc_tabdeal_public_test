from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class FeatureValue:
    name: str
    timestamp: datetime
    value: Optional[float]
