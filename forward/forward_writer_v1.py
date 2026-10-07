"""Branch-safe forward writer.

Decision writes are append-only. Outcomes are separate immutable artifacts
and are created exclusively, never rewritten.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class WriterConfig:
    journal_path: Path


class ForwardWriterV1:
    def __init__(self, journal):
        self.journal = journal

    def write_decision(self, record: Mapping[str, Any]) -> None:
        if record.get("decision") not in {"LONG", "SHORT", "NO_TRADE"}:
            raise ValueError("invalid forward decision")
        self.journal.append_decision(record)

    def write_outcome_artifact(
        self,
        record: Mapping[str, Any],
        path: Path,
        *,
        decision_exists: Callable[[str], bool] | None = None,
    ) -> None:
        event_id = record.get("event_id")
        outcome = record.get("outcome")
        if not event_id or outcome not in {"WIN", "LOSS", "BREAKEVEN", "CANCELLED"}:
            raise ValueError("invalid outcome artifact")
        if decision_exists is not None and not decision_exists(event_id):
            raise ValueError("outcome references unknown decision event_id")

        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(record)
        with path.open("x", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
