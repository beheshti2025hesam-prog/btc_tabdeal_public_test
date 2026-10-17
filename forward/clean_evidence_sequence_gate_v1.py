"""Sequence gate for clean forward evidence; opaque values are not ordering proof."""
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
    """Validate sequence syntax and exact raw replays without inventing semantics.

    This gate does not certify a stream as decision-safe. A downstream consumer
    that needs event ordering, identity, or continuity must require a separate
    verified, scope-matched capability contract.
    """

    def evaluate(self, records: list[dict[str, Any]]) -> EvidenceSequenceResult:
        gate = SequenceIntegrityV1()
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for record in records:
            try:
                event = gate.observe(record)
            except (TypeError, ValueError):
                rejected.append(record)
                return EvidenceSequenceResult(False, tuple(accepted), tuple(rejected), "INVALID_SEQUENCE")
            if event.status == "ACCEPTED":
                accepted.append(record)
            elif event.status == "EXACT_REPLAY":
                # Exact raw-byte replay is idempotent; sequence equality alone is not.
                continue
            else:
                rejected.append(record)
                return EvidenceSequenceResult(
                    False, tuple(accepted), tuple(rejected), event.reason or event.status
                )
        return EvidenceSequenceResult(True, tuple(accepted), tuple(rejected), "SEQUENCE_SEMANTICS_UNVERIFIED")
