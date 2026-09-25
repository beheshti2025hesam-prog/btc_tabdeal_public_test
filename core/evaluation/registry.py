"""Immutable evidence registry and stale-evidence detection.

This module records self-verifying evidence snapshots without mutating them.
It does not promote, rank, execute, size, leverage, or connect to a venue.
"""

from dataclasses import dataclass

from core.evaluation.evidence import EvidenceSnapshot


@dataclass(frozen=True)
class EvidenceRegistry:
    """Append-only registry represented as an immutable tuple of snapshots."""

    snapshots: tuple[EvidenceSnapshot, ...] = ()

    def append(self, snapshot: EvidenceSnapshot) -> "EvidenceRegistry":
        if not snapshot.verify():
            raise ValueError("cannot register an invalid evidence snapshot")
        if any(existing.digest == snapshot.digest for existing in self.snapshots):
            raise ValueError("duplicate evidence snapshot")
        return EvidenceRegistry(self.snapshots + (snapshot,))

    def latest(self) -> EvidenceSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None


@dataclass(frozen=True)
class EvidenceFreshness:
    fresh: bool
    reasons: tuple[str, ...]


class EvidenceRegistryValidator:
    """Validate evidence integrity, identity, and source-commit freshness."""

    PROJECT_NAME = "HES Trade Agent"
    OWNER = "Seyed Hesameddin Beheshti Shirazi"

    def validate(
        self,
        snapshot: EvidenceSnapshot,
        current_source_commit: str,
    ) -> EvidenceFreshness:
        reasons: list[str] = []

        if not snapshot.verify():
            reasons.append("snapshot_digest_invalid")
        if snapshot.project_name != self.PROJECT_NAME:
            reasons.append("project_identity_mismatch")
        if snapshot.owner != self.OWNER:
            reasons.append("owner_identity_mismatch")
        if snapshot.source_commit != current_source_commit:
            reasons.append("stale_source_commit")

        return EvidenceFreshness(fresh=not reasons, reasons=tuple(reasons))
