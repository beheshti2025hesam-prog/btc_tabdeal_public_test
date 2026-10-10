"""Fail-closed evidence gate for opaque source sequence metadata."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from pathlib import Path

from .sequence_integrity_v1 import SequenceIntegrityV1
from .source_evidence_registry_v1 import SourceEvidenceRegistryError, verify_source_evidence_bundle

DEFAULT_SOURCE_EVIDENCE_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "evidence" / "source_evidence_registry_v1.json"


@dataclass(frozen=True)
class EvidenceSequenceResult:
    safe: bool
    accepted: tuple[dict[str, Any], ...]
    rejected: tuple[dict[str, Any], ...]
    reason: str


class CleanEvidenceSequenceGateV1:
    """Never infer order or completeness from sequence values.

    Trusted evidence requires separately reviewed source-completeness and
    source-ordering evidence references. Both gates default to blocked.
    """

    def __init__(
        self,
        *,
        sequence_contract_verified: bool = False,
        sequence_contract_evidence_ref: str | None = None,
        source_completeness_verified: bool = False,
        source_completeness_evidence_ref: str | None = None,
        source_ordering_verified: bool = False,
        source_ordering_evidence_ref: str | None = None,
        source_evidence_registry_path: str | Path | None = None,
    ) -> None:
        self.sequence_contract_verified = bool(sequence_contract_verified and isinstance(sequence_contract_evidence_ref, str) and sequence_contract_evidence_ref.strip())
        self.sequence_contract_evidence_ref = sequence_contract_evidence_ref
        self.source_evidence_registry_path = Path(source_evidence_registry_path) if source_evidence_registry_path is not None else DEFAULT_SOURCE_EVIDENCE_REGISTRY_PATH
        self.source_completeness_verified = bool(
            source_completeness_verified
            and isinstance(source_completeness_evidence_ref, str)
            and source_completeness_evidence_ref.strip()
        )
        self.source_ordering_verified = bool(
            source_ordering_verified
            and isinstance(source_ordering_evidence_ref, str)
            and source_ordering_evidence_ref.strip()
        )

    def evaluate(self, records: list[dict[str, Any]]) -> EvidenceSequenceResult:
        if not records:
            return EvidenceSequenceResult(False, (), (), "NO_FORWARD_RECORDS")
        if not self.sequence_contract_verified:
            return EvidenceSequenceResult(False, (), tuple(records), "UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED")
        if not self.source_completeness_verified:
            return EvidenceSequenceResult(False, (), tuple(records), "SOURCE_COMPLETENESS_UNVERIFIED")
        if not self.source_ordering_verified:
            return EvidenceSequenceResult(False, (), tuple(records), "SOURCE_ORDERING_UNVERIFIED")
        try:
            verify_source_evidence_bundle(
                self.source_evidence_registry_path,
                sequence_contract_ref=self.sequence_contract_evidence_ref or "",
                source_completeness_ref=self.source_completeness_evidence_ref or "",
                source_ordering_ref=self.source_ordering_evidence_ref or "",
                source_scope="tabdeal-futures:BTC_USDT",
            )
        except SourceEvidenceRegistryError as exc:
            return EvidenceSequenceResult(False, (), tuple(records), exc.code)

        gate = SequenceIntegrityV1()
        observed: list[dict[str, Any]] = []
        for record in records:
            try:
                event = gate.observe(record)
            except (TypeError, ValueError):
                return EvidenceSequenceResult(False, (), tuple(records), "INVALID_SEQUENCE_TYPE")
            observed.append(record)
            if event.status != "ACCEPTED":
                return EvidenceSequenceResult(False, (), tuple(records), event.reason or event.status)

        # This generic gate imposes no numeric gap/order rule. Source-specific
        # validation must be implemented only from the reviewed contract.
        return EvidenceSequenceResult(True, tuple(observed), (), "SOURCE_CONTRACT_GATES_VERIFIED")
