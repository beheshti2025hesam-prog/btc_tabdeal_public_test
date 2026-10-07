"""Forward collector adapter boundary.

This module deliberately does NOT import or execute the legacy collector's
GitHub checkpoint/push path. It defines a branch-safe handoff contract for
fresh observations only.

The adapter remains disabled until an explicit runtime implementation is
wired and tested.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ForwardObservation:
    symbol: str
    price: float
    amount: float
    side: str
    observed_at: datetime
    sequence: int


class ForwardCollectorAdapterV1:
    """Fail-closed adapter for fresh forward observations."""

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled

    def accept(self, observations: Iterable[Mapping[str, object]]) -> tuple[ForwardObservation, ...]:
        if not self.enabled:
            raise RuntimeError(
                "Forward collector adapter is disabled until branch-safe runtime wiring is verified."
            )

        result: list[ForwardObservation] = []
        for item in observations:
            result.append(
                ForwardObservation(
                    symbol=str(item["symbol"]),
                    price=float(item["price"]),
                    amount=float(item["amount"]),
                    side=str(item["side"]),
                    observed_at=item["observed_at"],
                    sequence=int(item["sequence"]),
                )
            )
        return tuple(result)
