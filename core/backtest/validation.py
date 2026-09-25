"""Historical validation boundary with anti-leakage checks.

Execution-free validation of ordered feature/decision observations.
No orders, capital mutation, leverage, or live trading.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from core.backtest.engine import BacktestEngine, BacktestResult, BacktestSample


@dataclass(frozen=True)
class HistoricalObservation:
    timestamp: datetime
    sample: BacktestSample


class HistoricalValidation:
    """Validate temporal integrity, then replay observations deterministically."""

    def run(self, observations: Iterable[HistoricalObservation]) -> BacktestResult:
        rows = list(observations)
        previous: datetime | None = None
        for row in rows:
            ts = row.timestamp
            if ts.tzinfo is None or ts.utcoffset() is None:
                raise ValueError("observation timestamp must be timezone-aware")
            if row.sample.timestamp != ts:
                raise ValueError("sample timestamp must match observation timestamp")
            if previous is not None and ts < previous:
                raise ValueError("historical observations must be chronological")
            previous = ts
        return BacktestEngine().run(row.sample for row in rows)
