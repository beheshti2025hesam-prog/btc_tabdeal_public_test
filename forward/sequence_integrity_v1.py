"""Fail-closed sequence integrity state machine for forward observations."""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class SequenceEvent:
    sequence: int
    status: str
    reason: str | None = None
    diagnostic: dict[str, Any] | None = field(default=None, compare=False)


class SequenceIntegrityV1:
    """Tracks monotonic source sequence identifiers without repairing or reordering data.

Tabdeal sequence values are treated as ordered identifiers, not contiguous counters.
Continuity is enforced by rejecting regressions and conflicting duplicates; a numeric
jump is observable but is not, by itself, evidence of a missing market event.
"""

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

    @staticmethod
    def _digest(record: dict[str, Any]) -> str:
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _conflict_diagnostic(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        # Persist only normalized public market fields; never arbitrary input payloads.
        safe_fields = ("source", "symbol", "price", "amount", "side", "source_updated", "sequence")
        differing = [key for key in safe_fields if previous.get(key) != current.get(key)]
        previous_keys = set(previous)
        current_keys = set(current)
        other_fields_changed = sorted(
            key for key in (previous_keys | current_keys)
            if key not in safe_fields and previous.get(key) != current.get(key)
        )
        return {
            "diagnostic_schema": "hes_sequence_conflict_fingerprint_v1",
            "first_payload_sha256": SequenceIntegrityV1._digest(previous),
            "conflicting_payload_sha256": SequenceIntegrityV1._digest(current),
            "differing_fields": differing,
            "first_values": {key: previous.get(key) for key in differing},
            "conflicting_values": {key: current.get(key) for key in differing},
            "other_fields_changed": other_fields_changed,
        }

    def observe(self, record: dict[str, Any]) -> SequenceEvent:
        seq = self._seq(record.get("sequence"))
        previous = self._records.get(seq)
        if previous is not None:
            if previous == record:
                return SequenceEvent(seq, "IDEMPOTENT_DUPLICATE")
            return SequenceEvent(
                seq, "REJECT_STREAM", "CONFLICTING_DUPLICATE_SEQUENCE",
                self._conflict_diagnostic(previous, record),
            )

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
