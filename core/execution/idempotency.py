"""Execution idempotency contract for HES Trade Agent.

This module defines deterministic request identity and duplicate handling only.
It performs no execution, venue connection, capital mutation, or live trading.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IdempotencyKey:
    """Stable identity for one logical execution request."""

    request_id: str


@dataclass(frozen=True)
class IdempotencyRecord:
    """Immutable record of an already-seen request outcome."""

    key: IdempotencyKey
    accepted: bool
    reason: str


class IdempotencyRegistry:
    """Execution-free registry that rejects duplicate request identities."""

    def __init__(self) -> None:
        self._records: dict[IdempotencyKey, IdempotencyRecord] = {}

    def register(
        self,
        key: IdempotencyKey,
        *,
        accepted: bool,
        reason: str,
    ) -> IdempotencyRecord:
        """Record a request once; repeated identities return the original record."""
        existing = self._records.get(key)
        if existing is not None:
            return existing

        record = IdempotencyRecord(
            key=key,
            accepted=accepted,
            reason=reason,
        )
        self._records[key] = record
        return record

    def contains(self, key: IdempotencyKey) -> bool:
        """Return whether this logical request has already been registered."""
        return key in self._records

    def get(self, key: IdempotencyKey) -> IdempotencyRecord | None:
        """Return the immutable prior result, if present."""
        return self._records.get(key)
