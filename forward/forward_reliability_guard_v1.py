"""Forward reliability guard: explicit, fail-closed invariants for live observation paths."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

@dataclass(frozen=True)
class ReliabilityEvent:
    code: str
    severity: str
    message: str
    observed_at: str

class ReliabilityGuardV1:
    """Small deterministic guard; no I/O, persistence, networking, or execution."""

    def validate_timestamp(self, value: datetime, *, as_of: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if value.astimezone(timezone.utc) > as_of.astimezone(timezone.utc):
            raise ValueError("future source observation")

    def validate_sequence(self, sequence: Any) -> int:
        try:
            seq = int(sequence)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid sequence") from exc
        if seq < 0:
            raise ValueError("invalid sequence")
        return seq

    def validate_duplicate(self, previous: dict[str, Any] | None, current: dict[str, Any]) -> None:
        if previous is None:
            return
        if previous != current:
            raise ValueError("conflicting duplicate sequence")
        raise ValueError("duplicate sequence")

    def require_reason(self, reason: str) -> str:
        reason = str(reason).strip()
        if not reason:
            raise ValueError("rejection reason required")
        return reason
