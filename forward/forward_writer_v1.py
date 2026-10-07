"""Branch-safe forward writer.

Never performs a git push and never targets main implicitly. It writes only
through an injected append-only journal implementation.
"""
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class WriterConfig:
    journal_path: Path

class ForwardWriterV1:
    def __init__(self, journal):
        self.journal=journal

    def write_decision(self, record: dict) -> None:
        if record.get("decision") not in {"LONG","SHORT","NO_TRADE"}:
            raise ValueError("invalid forward decision")
        self.journal.append_decision(record)

    def write_outcome_artifact(self, record: dict, path: Path) -> None:
        if not record.get("event_id") or record.get("outcome") not in {"WIN","LOSS","BREAKEVEN","CANCELLED"}:
            raise ValueError("invalid outcome artifact")
        if path.exists():
            raise FileExistsError("outcome artifact already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(__import__("json").dumps(record, sort_keys=True)+"\n", encoding="utf-8")
