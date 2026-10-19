"""Lossless adapter from producer evidence to canonical promotion evidence.

EvidenceResult remains a producer-layer contract. This module canonicalizes its
boolean gate state into EvidenceSnapshot while retaining producer details as
immutable diagnostics. It never promotes, executes, or mutates raw data.
"""

from dataclasses import dataclass

from core.evaluation.evidence import EvidenceSnapshot
from core.evaluation.producer import EvidenceResult


@dataclass(frozen=True)
class CanonicalEvidence:
    """Canonical snapshot plus lossless producer diagnostics."""

    snapshot: EvidenceSnapshot
    details: tuple[tuple[str, str], ...]


def canonicalize(
    results: tuple[EvidenceResult, ...] | list[EvidenceResult],
    *,
    project_name: str,
    owner: str,
    source_commit: str,
) -> CanonicalEvidence:
    """Convert producer results into the canonical evidence contract.

    Duplicate gate names are rejected so one producer cannot silently overwrite
    another producer's evidence.
    """

    evidence: dict[str, bool] = {}
    details: list[tuple[str, str]] = []

    for result in results:
        if not isinstance(result, EvidenceResult):
            raise TypeError("canonicalize requires EvidenceResult items")
        if result.gate_name in evidence:
            raise ValueError(f"duplicate evidence gate: {result.gate_name}")
        evidence[result.gate_name] = result.passed
        details.append((result.gate_name, result.details))

    snapshot = EvidenceSnapshot.create(
        project_name=project_name,
        owner=owner,
        source_commit=source_commit,
        evidence=evidence,
    )
    return CanonicalEvidence(snapshot=snapshot, details=tuple(details))
