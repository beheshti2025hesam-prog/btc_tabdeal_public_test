"""Fail-closed evidence gate for opaque source sequence metadata."""
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
    """Never infer order or completeness from sequence values.

    A caller may set source_completeness_verified only when it has a reviewed,
    exact-feed evidence pin. The default is intentionally blocked.
    """

    def __init__(
        self,
        *,
        source_completeness_verified: bool = False,
        source_completeness_evidence_ref: str | None = None,
    ) -> None:
        self.source_completeness_verified = bool(
            source_completeness_verified and source_completeness_evidence_ref
        )

    def evaluate(self, records: list[dict[str, Any]]) -> EvidenceSequenceResult:
        if not records:
            return EvidenceSequenceResult(False, (), (), "NO_FORWARD_RECORDS")

        gate = SequenceIntegrityV1()
        observed: list[dict[str, Any]] = []
        for record in records:
            try:
                event = gate.observe(record)
            except (TypeError, ValueError):
                return EvidenceSequenceResult(
                    False, (), tuple(records), "INVALID_SEQUENCE_TYPE"
                )
            observed.append(record)
            if event.status != "ACCEPTED":
                return EvidenceSequenceResult(
                    False, (), tuple(records), event.reason or event.status
                )

        if not self.source_completeness_verified:
            return EvidenceSequenceResult(
                False, (), tuple(records), "SOURCE_COMPLETENESS_UNVERIFIED"
            )

        # A verified source contract must be interpreted by its source-specific
        # adapter. This generic gate deliberately imposes no numeric gap/order rule.
        return EvidenceSequenceResult(True, tuple(observed), (), "SEQUENCE_CONTRACT_VERIFIED")
