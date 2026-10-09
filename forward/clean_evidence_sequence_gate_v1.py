"""Sequence gate for clean forward evidence; anomalies never become evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .sequence_integrity_v1 import SequenceIntegrityV1


@dataclass(frozen=True)
class EvidenceSequenceResult:
    safe: bool
    accepted: tuple[dict[str, Any], ...]
    rejected: tuple[dict[str, Any], ...]
    reason: str


class CleanEvidenceSequenceGateV1:
    """Stricter evidence boundary: require contiguous values until source semantics are documented."""

    def evaluate(self, records: list[dict[str, Any]]) -> EvidenceSequenceResult:
        gate = SequenceIntegrityV1()
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        last_accepted_sequence: int | None = None
        for record in records:
            try:
                event = gate.observe(record)
            except (TypeError, ValueError):
                rejected.append(record)
                return EvidenceSequenceResult(False, tuple(accepted), tuple(rejected), "INVALID_SEQUENCE")
            if event.status == "ACCEPTED":
                if last_accepted_sequence is not None and event.sequence != last_accepted_sequence + 1:
                    rejected.append(record)
                    return EvidenceSequenceResult(
                        False, tuple(accepted), tuple(rejected), "SEQUENCE_GAP_UNVERIFIED"
                    )
                accepted.append(record)
                last_accepted_sequence = event.sequence
            elif event.status == "IDEMPOTENT_DUPLICATE":
                continue
            else:
                rejected.append(record)
                return EvidenceSequenceResult(
                    False, tuple(accepted), tuple(rejected), event.reason or event.status
                )
        return EvidenceSequenceResult(True, tuple(accepted), tuple(rejected), "SEQUENCE_SAFE")
