"""Crash-safe checkpoint boundary: metadata only, never continuity proof."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import hashlib, json

@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    segment_id: int
    created_at: str
    digest: str

class CrashSafeCheckpointV1:
    def __init__(self) -> None:
        self._written: set[str] = set()

    @staticmethod
    def _utc(value: datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def create(self, *, checkpoint_id: str, segment_id: int, created_at: datetime, state: dict[str, Any]) -> Checkpoint:
        if not checkpoint_id:
            raise ValueError("checkpoint_id required")
        if segment_id < 1:
            raise ValueError("segment_id must be positive")
        if checkpoint_id in self._written:
            raise ValueError("duplicate checkpoint")
        # State is descriptive only; sequence continuity is explicitly excluded.
        forbidden={"resume_sequence","last_sequence","sequence_adjacency","continuity_proof"}
        if forbidden.intersection(state):
            raise ValueError("checkpoint cannot contain continuity proof")
        stamp=self._utc(created_at)
        payload={"checkpoint_id":checkpoint_id,"segment_id":segment_id,"created_at":stamp,"state":state}
        raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
        digest=hashlib.sha256(raw).hexdigest()
        self._written.add(checkpoint_id)
        return Checkpoint(checkpoint_id,segment_id,stamp,digest)
