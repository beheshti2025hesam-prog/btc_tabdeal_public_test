"""Extensible evidence gate schema.

The schema defines what a required evidence gate means without defining
strategy-specific thresholds or performing promotion. It is deliberately
small so new evidence producers can be added without changing the gate API.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceGate:
    """Immutable declaration of one evidence requirement."""

    name: str
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Evidence gate name must be non-empty.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Evidence gate description must be non-empty.")


@dataclass(frozen=True)
class EvidenceGateSchema:
    """Immutable, deterministic collection of required evidence gates."""

    gates: tuple[EvidenceGate, ...]

    def __post_init__(self) -> None:
        if not self.gates:
            raise ValueError("Evidence gate schema must contain at least one gate.")

        names = [gate.name for gate in self.gates]
        if len(names) != len(set(names)):
            raise ValueError("Evidence gate names must be unique.")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(gate.name for gate in self.gates)

    def as_required_evidence(self) -> tuple[str, ...]:
        """Return the stable gate-name contract consumed by PromotionGate."""
        return self.names
