"""Fail-closed observations for opaque source sequence metadata.

The Tabdeal Futures sequence contract is undocumented. This module therefore
preserves native scalar values but does not infer numeric ordering, continuity,
trade identity, or redelivery from them. Any repeated native sequence is
blocked for dependent consumers until a source-specific contract is reviewed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class SequenceEvent:
    sequence: int | str
    status: str
    reason: str | None = None
    diagnostic: dict[str, Any] | None = field(default=None, compare=False)


class SequenceIntegrityV1:
    """Conservatively observe opaque sequence values without interpreting them.

    \`\`last_sequence\`\` is retained for compatibility and means only the most
    recently observed native value. It does not imply monotonicity or ordering.
    Every observed record is retained in bounded in-memory state for this
    connection epoch. Durable evidence persistence remains the caller's duty.
    """

    def __init__(self, *, max_records: int = 100_000) -> None:
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        self.last_sequence: int | str | None = None
        self._records: list[dict[str, Any]] = []
        self._first_by_sequence: dict[tuple[str, int | str], dict[str, Any]] = {}

    @staticmethod
    def _seq(value: Any) -> int | str:
        # Do not coerce native values: 7, "7", and "007" are distinct.
        # bool is excluded even though bool is a subclass of int in Python.
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("invalid sequence")
        if isinstance(value, str) and not value:
            raise ValueError("invalid sequence")
        return value

    @staticmethod
    def _sequence_key(value: int | str) -> tuple[str, int | str]:
        return (type(value).__name__, value)

    @staticmethod
    def _digest(record: dict[str, Any]) -> str:
        canonical = json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _repeat_diagnostic(
        previous: dict[str, Any], current: dict[str, Any]
    ) -> dict[str, Any]:
        # Store hashes and allowlisted field deltas, not arbitrary raw payloads.
        safe_fields = (
            "source", "symbol", "price", "amount", "side",
            "source_updated", "sequence",
        )
        differing = [
            key for key in safe_fields if previous.get(key) != current.get(key)
        ]
        previous_keys = set(previous)
        current_keys = set(current)
        other_fields_changed = sorted(
            key
            for key in (previous_keys | current_keys)
            if key not in safe_fields and previous.get(key) != current.get(key)
        )
        return {
            "diagnostic_schema": "hes_sequence_reuse_observation_v2",
            "first_payload_sha256": SequenceIntegrityV1._digest(previous),
            "observed_payload_sha256": SequenceIntegrityV1._digest(current),
            "same_payload": previous == current,
            "differing_fields": differing,
            "first_values": {key: previous.get(key) for key in differing},
            "observed_values": {key: current.get(key) for key in differing},
            "other_fields_changed": other_fields_changed,
        }

    def observe(self, record: dict[str, Any]) -> SequenceEvent:
        seq = self._seq(record.get("sequence"))
        current = dict(record)

        if len(self._records) >= self.max_records:
            return SequenceEvent(
                seq,
                "REJECT_STREAM",
                "SEQUENCE_STATE_BOUND_EXCEEDED",
                {"max_records": self.max_records},
            )

        key = self._sequence_key(seq)
        previous = self._first_by_sequence.get(key)
        # Keep every observation, including identical payloads. Sequence alone
        # cannot prove a duplicate delivery, so dependent snapshots fail closed.
        self._records.append(current)
        self.last_sequence = seq

        if previous is not None:
            diagnostic = self._repeat_diagnostic(previous, current)
            reason = (
                "REPEATED_SEQUENCE_IDENTITY_UNPROVEN"
                if previous == current
                else "SOURCE_SEQUENCE_REUSE_OBSERVED_ORDERING_SEMANTICS_UNKNOWN"
            )
            return SequenceEvent(seq, "REJECT_STREAM", reason, diagnostic)

        self._first_by_sequence[key] = current
        return SequenceEvent(seq, "ACCEPTED")

    def reset_for_reconnect(self) -> None:
        """Start a new connection epoch; callers must preserve prior evidence."""
        self.last_sequence = None
        self._records.clear()
        self._first_by_sequence.clear()
