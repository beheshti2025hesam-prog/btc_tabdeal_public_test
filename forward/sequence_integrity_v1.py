"""Capability-gated sequence handling for forward observations.

Opaque sequence-like fields are not treated as identity, order, or continuity
proof. Strict checks require an explicit, independently justified capability.
"""
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
    """Track sequence values only to the extent their semantics are authorized.

    The default mode is opaque: no ordering, contiguity, or identity/conflict
    inference is made from the sequence value. Exact replay suppression is
    enabled only when the transport supplies the SHA-256 of the raw payload.
    Set sequence_semantics_verified=True only for an adapter whose exact
    identity/order contract has been verified for the relevant scope.
    """

    def __init__(
        self, *, max_records: int = 100_000,
        sequence_semantics_verified: bool = False,
    ) -> None:
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        if type(sequence_semantics_verified) is not bool:
            raise ValueError("sequence_semantics_verified must be bool")
        self.max_records = max_records
        self.sequence_semantics_verified = sequence_semantics_verified
        self.last_sequence: int | None = None
        self._records: dict[int, dict[str, Any]] = {}
        self._opaque_payload_hashes: set[str] = set()
        self._opaque_record_count = 0

    @staticmethod
    def _seq(value: Any) -> int:
        # Reject bool (an int subclass), floats, whitespace, Unicode digits,
        # and coercible non-wire values before any state can be mutated.
        if type(value) is int:
            seq = value
        elif isinstance(value, str) and value.isascii() and value.isdigit():
            seq = int(value)
        else:
            raise ValueError("invalid sequence")
        if seq < 0:
            raise ValueError("invalid sequence")
        return seq

    @staticmethod
    def _digest(record: dict[str, Any]) -> str:
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _conflict_diagnostic(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        safe_fields = ("source", "symbol", "price", "amount", "side", "source_updated", "sequence")
        differing = [key for key in safe_fields if previous.get(key) != current.get(key)]
        previous_keys, current_keys = set(previous), set(current)
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

        if not self.sequence_semantics_verified:
            # A digest is replay evidence only when computed from the raw wire
            # payload at the transport boundary. Never substitute normalized
            # fields or the opaque sequence value for that evidence.
            raw_digest = record.get("raw_payload_sha256")
            if isinstance(raw_digest, str) and len(raw_digest) == 64 and all(
                ch in "0123456789abcdef" for ch in raw_digest
            ):
                if raw_digest in self._opaque_payload_hashes:
                    return SequenceEvent(seq, "EXACT_REPLAY", "RAW_PAYLOAD_SHA256_MATCH")
                if self._opaque_record_count >= self.max_records:
                    return SequenceEvent(
                        seq, "REJECT_STREAM", "SEQUENCE_STATE_BOUND_EXCEEDED",
                        {"max_records": self.max_records},
                    )
                self._opaque_payload_hashes.add(raw_digest)
            elif self._opaque_record_count >= self.max_records:
                return SequenceEvent(
                    seq, "REJECT_STREAM", "SEQUENCE_STATE_BOUND_EXCEEDED",
                    {"max_records": self.max_records},
                )
            self._opaque_record_count += 1
            self.last_sequence = seq  # diagnostic only; never compared or used for ordering
            return SequenceEvent(seq, "ACCEPTED", "SEQUENCE_SEMANTICS_UNKNOWN")

        previous = self._records.get(seq)
        if previous is not None:
            if previous == record:
                return SequenceEvent(seq, "IDEMPOTENT_DUPLICATE")
            return SequenceEvent(
                seq, "REJECT_STREAM", "CONFLICTING_DUPLICATE_SEQUENCE",
                self._conflict_diagnostic(previous, record),
            )
        if self.last_sequence is not None and seq < self.last_sequence:
            return SequenceEvent(seq, "ANOMALY", "OUT_OF_ORDER_SEQUENCE")
        if len(self._records) >= self.max_records:
            return SequenceEvent(
                seq, "REJECT_STREAM", "SEQUENCE_STATE_BOUND_EXCEEDED",
                {"max_records": self.max_records},
            )
        self._records[seq] = dict(record)
        self.last_sequence = seq
        return SequenceEvent(seq, "ACCEPTED")

    def reset_for_reconnect(self) -> None:
        """Clear continuity/replay state; never fabricate continuity across reconnect."""
        self.last_sequence = None
        self._records.clear()
        self._opaque_payload_hashes.clear()
        self._opaque_record_count = 0
