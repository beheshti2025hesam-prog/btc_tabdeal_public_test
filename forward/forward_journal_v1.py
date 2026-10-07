"""Append-only forward journal primitives.

This reference writer keeps decision time and outcome time separate. It does
not mutate an existing decision because of a later outcome.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
from pathlib import Path

@dataclass(frozen=True)
class JournalRecord:
    event_id: str
    observed_at: str
    symbol: str
    timeframe: str
    decision: str
    evidence_source: tuple[str, ...]
    outcome: str | None = None
    closed_at: str | None = None

class ForwardJournalV1:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        ids=set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ids.add(json.loads(line)["event_id"])
        return ids

    def append_decision(self, record: JournalRecord) -> None:
        if record.decision not in {"LONG","SHORT","NO_TRADE"}:
            raise ValueError("invalid decision")
        if record.event_id in self._ids():
            raise ValueError("duplicate event_id")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")

    def append_outcome(self, *, event_id: str, outcome: str, closed_at: str) -> None:
        raise NotImplementedError(
            "Outcome mutation requires a separate immutable outcome artifact; "
            "do not rewrite the original decision record."
        )
