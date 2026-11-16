"""Observe opaque Tabdeal sequence metadata without identity or ordering inference."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SequenceEvent:
    sequence: int | str | None
    status: str
    reason: str | None = None
    diagnostic: dict[str, Any] | None = None


class SequenceIntegrityV1:
    """Preserve each observation; sequence values never deduplicate or veto trades.

    The sequence value is optional informational metadata. This class does not
    compare values, infer gaps/order, or classify repeated values as duplicates.
    Completeness and ordering remain separate source-evidence gates.
    """

    def __init__(self, *, max_records: int = 100_000) -> None:
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        self.last_sequence: int | str | None = None
        self._records: list[dict[str, Any]] = []

    @staticmethod
    def _seq(value: Any) -> int | str | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("invalid sequence")
        if value == "":
            raise ValueError("invalid sequence")
        return value

    def observe(self, record: dict[str, Any]) -> SequenceEvent:
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")
        seq = self._seq(record.get("sequence"))
        if len(self._records) >= self.max_records:
            return SequenceEvent(
                seq,
                "REJECT_STREAM",
                "SEQUENCE_OBSERVATION_BOUND_EXCEEDED",
                {"max_records": self.max_records},
            )
        self._records.append(dict(record))
        self.last_sequence = seq
        return SequenceEvent(seq, "ACCEPTED")

    def reset_for_reconnect(self) -> None:
        """Start a new local observation epoch; callers retain prior durable evidence."""
        self.last_sequence = None
        self._records.clear()
