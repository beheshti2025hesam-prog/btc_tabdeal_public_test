"""Compatibility facade for the capability-driven sequence engine.

The former universal monotonic/duplicate assumptions were removed. Callers
must provide capabilities resolved from a pinned, exact-scope registry record.
"""
from __future__ import annotations

from .sequence_semantics_v1 import (
    SequenceCapabilitiesV1,
    SequenceEventV2 as SequenceEvent,
    SequenceIntegrityV2,
)


class SequenceIntegrityV1:
    def __init__(
        self,
        *,
        capabilities: SequenceCapabilitiesV1 | None = None,
        max_records: int = 100_000,
    ) -> None:
        self._engine = SequenceIntegrityV2(
            capabilities, max_records=max_records
        )

    @property
    def last_sequence(self) -> int | None:
        return self._engine.last_sequence

    def observe(self, record: dict):
        return self._engine.observe(record)

    def reset_for_reconnect(self) -> None:
        self._engine.reset_for_reconnect()
