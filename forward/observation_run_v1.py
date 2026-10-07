"""Immutable metadata record for an observation-only forward run."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path


@dataclass(frozen=True)
class ObservationRunV1:
    run_id: str
    started_at: datetime
    policy_id: str
    policy_version: str
    symbol: str
    timeframe: str
    source: str

    def as_record(self) -> dict:
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        return {
            **asdict(self),
            "started_at": self.started_at.isoformat(),
            "mode": "OBSERVATION_ONLY",
            "decision_mode": "NO_TRADE_ONLY",
            "execution_enabled": False,
            "historical_inputs_allowed": False,
        }

    def write_once(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        record = self.as_record()
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with target.open("x", encoding="utf-8") as handle:
            handle.write(line)
