"""Append-only journal for immutable forward observation identities."""
from __future__ import annotations
import json
import os
from pathlib import Path
from dataclasses import asdict
from .observation_snapshot_identity_v1 import ObservationSnapshotIdentity


class ObservationJournalV1:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, snapshot: ObservationSnapshotIdentity) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(snapshot), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def read(self) -> list[ObservationSnapshotIdentity]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open("r", encoding="utf-8") as f:
            for raw in f:
                if not raw.strip():
                    continue
                data=json.loads(raw)
                out.append(ObservationSnapshotIdentity(**data))
        return out
