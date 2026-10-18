"""Explicit boundary between legacy historical rows and forward evidence."""
from __future__ import annotations
from typing import Any, Mapping

LEGACY_FORWARD_BOUNDARY_V1 = "LEGACY_FORWARD_BOUNDARY_V1"

class LegacyForwardContractError(ValueError):
    """A legacy/unproven row attempted to cross into the forward evidence path."""
    def __init__(self, code: str = LEGACY_FORWARD_BOUNDARY_V1) -> None:
        self.code = code
        super().__init__(code)

def require_forward_evidence_record(record: Mapping[str, Any]) -> None:
    """Fail closed unless a row carries the explicit forward transport contract.

    This is a boundary assertion, not a converter. It never normalizes or orders
    sequence values. It does not authenticate transport provenance by itself.
    """
    if not isinstance(record, Mapping):
        raise LegacyForwardContractError("FORWARD_RECORD_NOT_MAPPING")
    if record.get("source") != "tabdeal_ws_forward_v1":
        raise LegacyForwardContractError(LEGACY_FORWARD_BOUNDARY_V1)
    if "source_updated" not in record:
        raise LegacyForwardContractError("FORWARD_SOURCE_TIMESTAMP_MISSING")
    if "sequence" not in record:
        raise LegacyForwardContractError("FORWARD_SEQUENCE_IDENTITY_MISSING")
    return None
