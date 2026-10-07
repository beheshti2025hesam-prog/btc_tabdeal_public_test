"""Fail-closed sequence integrity state machine for forward observations."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SequenceEvent:
    sequence: int
    status: str
    reason: str | None = None


class SequenceIntegrityV1:
    """Tracks sequence continuity without repairing or reordering source data."""

    def __init__(self) -> None:
        self.last_sequence: int | None = None
        self._records: dict[int, dict[str, Any]] = {}

    @staticmethod
    def _seq(value: Any) -> int:
        try:
            seq = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid sequence") from exc
        if seq < 0:
            raise ValueError("invalid sequence")
        return seq

    def observe(self, record: dict[str, Any]) -> SequenceEvent:
        seq = self._seq(record.get("sequence"))
        previous = self._records.get(seq)
        if previous is not None:
            if previous == record:
                return SequenceEvent(seq, "IDEMPOTENT_DUPLICATE")
            return SequenceEvent(seq, "REJECT_STREAM", "CONFLICTING_DUPLICATE_SEQUENCE")

        if self.last_sequence is not None:
            if seq < self.last_sequence:
                return SequenceEvent(seq, "ANOMALY", "OUT_OF_ORDER_SEQUENCE")
        self._records[seq] = dict(record)
        self.last_sequence = seq
        return SequenceEvent(seq, "ACCEPTED")

    def reset_for_reconnect(self) -> None:
        """Clear continuity only; never fabricate continuity across reconnect."""
        self.last_sequence = None
        self._records.clear()
