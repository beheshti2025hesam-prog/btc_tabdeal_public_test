"""Capability-driven sequence gate for clean forward evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .sequence_semantics_v1 import SequenceCapabilitiesV1, SequenceIntegrityV2


@dataclass(frozen=True)
class EvidenceSequenceResult:
    safe: bool
    accepted: tuple[dict[str, Any], ...]
    rejected: tuple[dict[str, Any], ...]
    reason: str


class CleanEvidenceSequenceGateV1:
    """Unknown semantics block; numeric gaps block only under a contiguous contract."""

    def evaluate(
        self,
        records: list[dict[str, Any]],
        *,
        capabilities: SequenceCapabilitiesV1 | None = None,
    ) -> EvidenceSequenceResult:
        gate = SequenceIntegrityV2(capabilities)
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for record in records:
            event = gate.observe(record)
            if event.status == "ACCEPTED":
                accepted.append(record)
            elif event.status == "IDEMPOTENT_DUPLICATE":
                continue
            else:
                rejected.append(record)
                return EvidenceSequenceResult(
                    False, tuple(accepted), tuple(rejected),
                    event.reason or event.status,
                )
        return EvidenceSequenceResult(True, tuple(accepted), tuple(rejected), "SEQUENCE_SAFE")
