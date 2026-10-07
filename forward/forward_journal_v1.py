"""Append-only forward journal primitives.

Decision records are immutable. Later outcomes are written to separate
immutable artifacts and never mutate the original decision record.
"""
from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Mapping


DECISIONS = {"LONG", "SHORT", "NO_TRADE"}
OUTCOMES = {"OPEN", "WIN", "LOSS", "BREAKEVEN", "CANCELLED", None}
REQUIRED_FIELDS = {
    "event_id", "observed_at", "symbol", "timeframe", "decision",
    "evidence_source",
}


def _validate_decision_record(record: Mapping[str, Any]) -> None:
    missing = sorted(REQUIRED_FIELDS - set(record))
    if missing:
        raise ValueError(f"missing journal fields: {','.join(missing)}")
    if record["decision"] not in DECISIONS:
        raise ValueError("invalid decision")
    if not isinstance(record["event_id"], str) or not record["event_id"]:
        raise ValueError("event_id is required")
    if not isinstance(record["evidence_source"], (str, list, tuple)):
        raise ValueError("evidence_source is required")
    # A decision journal entry is contemporaneous. Any non-null future outcome
    # presented at decision-journal time is forbidden.
    if "outcome" in record and record["outcome"] is not None:
        raise ValueError("future outcome leakage: decision record must have outcome=None")
    if "closed_at" in record and record["closed_at"] is not None:
        raise ValueError("future outcome leakage: decision record must have closed_at=None")


class ForwardJournalV1:
    """Single-writer append-only decision journal.

    The writer accepts the complete v1 journal mapping emitted by the decision
    layer. It validates identity and never rewrites an existing event.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        ids: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            event_id = item.get("event_id")
            if event_id:
                ids.add(event_id)
        return ids

    def append_decision(self, record: Mapping[str, Any]) -> None:
        _validate_decision_record(record)
        if record["event_id"] in self._ids():
            raise ValueError("duplicate event_id")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(record)
        payload.setdefault("outcome", None)
        payload.setdefault("closed_at", None)

        # Append-only: never rewrite a prior decision.
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()

    def append_outcome(self, *, event_id: str, outcome: str, closed_at: str) -> None:
        raise NotImplementedError(
            "Outcome mutation requires a separate immutable outcome artifact; "
            "do not rewrite the original decision record."
        )
