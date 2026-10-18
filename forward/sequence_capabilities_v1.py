"""Capability-gated sequence decisions; unknown semantics never imply ordering."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REGISTRY = Path(__file__).with_name("exchange_sequence_semantics_registry_v1.json")
_TRUE_CAPABILITY = "DOCUMENTED"


def load_registry() -> dict[str, Any]:
    """Load the checked-in research registry without inferring missing semantics."""
    registry = json.loads(_REGISTRY.read_text(encoding="utf-8"))
    if registry.get("schema") != "hes_exchange_sequence_semantics_registry_v1":
        raise ValueError("unsupported sequence semantics registry")
    if registry.get("status") != "RESEARCH_ONLY":
        raise ValueError("sequence semantics registry is not research-only")
    return registry


def get_record(record_id: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an exact adapter record; unknown IDs fail closed."""
    active = registry if registry is not None else load_registry()
    matches = [record for record in active.get("records", []) if record.get("id") == record_id]
    if len(matches) != 1:
        raise KeyError(f"sequence semantics record must be unique: {record_id}")
    return matches[0]


def capability_enabled(
    record_id: str,
    capability: str,
    *,
    registry: dict[str, Any] | None = None,
) -> bool:
    """Enable a capability only when the exact record says DOCUMENTED.

    UNKNOWN, UNSUPPORTED, missing records, missing fields, and malformed values
    do not authorize ordering, identity conflict rejection, or gap detection.
    """
    if capability not in {
        "event_identity",
        "ordered",
        "contiguous",
        "gap_detection",
        "cross_reconnect_comparable",
        "snapshot_delta_bridge",
    }:
        return False
    try:
        record = get_record(record_id, registry)
    except (KeyError, ValueError, OSError, json.JSONDecodeError):
        return False
    capabilities = record.get("capabilities")
    if not isinstance(capabilities, dict):
        return False
    return capabilities.get(capability) == _TRUE_CAPABILITY


def can_detect_gap(record_id: str, *, registry: dict[str, Any] | None = None) -> bool:
    return capability_enabled(record_id, "gap_detection", registry=registry)


def can_reject_conflicting_identity(
    record_id: str, *, registry: dict[str, Any] | None = None
) -> bool:
    return capability_enabled(record_id, "event_identity", registry=registry)


def can_compare_across_reconnect(
    record_id: str, *, registry: dict[str, Any] | None = None
) -> bool:
    return capability_enabled(record_id, "cross_reconnect_comparable", registry=registry)
