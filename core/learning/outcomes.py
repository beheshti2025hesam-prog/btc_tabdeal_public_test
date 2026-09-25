"""Deterministic, dependency-free outcome learning v1.

This is not a predictive ML model. It is a transparent online statistics layer
that can feed later promotion/ML gates without changing raw data or executing orders.
"""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class OutcomeStats:
    key: str
    observations: int
    wins: int
    losses: int
    total_pnl: float

    @property
    def win_rate(self) -> float:
        return self.wins / self.observations if self.observations else 0.0

    @property
    def expectancy(self) -> float:
        return self.total_pnl / self.observations if self.observations else 0.0


class OutcomeLearner:
    """Accumulate immutable-style outcome statistics keyed by a strategy context."""

    def __init__(self) -> None:
        self._stats: dict[str, list[float | int]] = {}

    def observe(self, key: str, pnl: float) -> OutcomeStats:
        if not key.strip():
            raise ValueError("key must not be empty")
        if not isfinite(pnl):
            raise ValueError("pnl must be finite")
        state = self._stats.setdefault(key, [0, 0, 0, 0.0])
        state[0] += 1
        if pnl > 0:
            state[1] += 1
        elif pnl < 0:
            state[2] += 1
        state[3] += pnl
        return self.stats(key)

    def stats(self, key: str) -> OutcomeStats:
        state = self._stats.get(key, [0, 0, 0, 0.0])
        return OutcomeStats(key, int(state[0]), int(state[1]), int(state[2]), float(state[3]))

    def snapshot(self) -> tuple[OutcomeStats, ...]:
        return tuple(self.stats(key) for key in sorted(self._stats))
