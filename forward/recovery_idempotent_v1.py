"""Restart/reconnect-safe forward continuity controller."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .sequence_integrity_v1 import SequenceIntegrityV1

@dataclass(frozen=True)
class RecoveryEvent:
    segment_id: int
    status: str
    reason: str | None = None

class ForwardRecoveryControllerV1:
    def __init__(self) -> None:
        self.segment_id = 0
        self.sequence = SequenceIntegrityV1()
        self.reconnects = 0

    def start(self) -> RecoveryEvent:
        self.segment_id += 1
        self.sequence.reset_for_reconnect()
        return RecoveryEvent(self.segment_id, "SEGMENT_STARTED")

    def reconnect(self) -> RecoveryEvent:
        self.reconnects += 1
        self.segment_id += 1
        self.sequence.reset_for_reconnect()
        return RecoveryEvent(self.segment_id, "CONTINUITY_RESET", "TRANSPORT_RECONNECT")

    def restart(self) -> RecoveryEvent:
        self.segment_id += 1
        self.sequence.reset_for_reconnect()
        return RecoveryEvent(self.segment_id, "CONTINUITY_RESET", "PROCESS_RESTART")

    def observe(self, record: dict[str, Any]):
        return self.sequence.observe(record)
