"""Capability-driven sequence semantics registry (candidate, fail-closed).

A sequence-like field has no semantics unless an exact venue/product/endpoint/
channel/message/field/protocol contract says so and carries capability-specific
primary evidence. The registry may be consumed by guards to deny unsafe paths;
it grants no positive capabilities in its current revision.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

REGISTRY_SCHEMA = "hes_sequence_semantics_registry_v1"
UNKNOWN = "unknown"
CAPABILITIES = (
    "event_identity_unique",
    "ordered_within_scope",
    "contiguous_within_scope",
    "gap_detectable",
    "cross_reconnect_comparable",
    "book_range_gap_detection",
    "snapshot_bootstrap",
)


class RegistryError(ValueError):
    pass


class SequenceSemanticsRegistryV1:
    def __init__(self, payload: Mapping[str, Any]):
        if payload.get("schema") != REGISTRY_SCHEMA:
            raise RegistryError("REGISTRY_SCHEMA_MISMATCH")
        revision = payload.get("revision")
        if type(revision) is not int or revision < 1:
            raise RegistryError("UNSUPPORTED_REGISTRY_REVISION")
        self.revision = revision
        records = payload.get("records")
        if not isinstance(records, list):
            raise RegistryError("REGISTRY_RECORDS_INVALID")
        self.payload = dict(payload)
        self._records: dict[tuple[str, ...], dict[str, Any]] = {}
        for item in records:
            key = self._key(item)
            if key in self._records:
                raise RegistryError("DUPLICATE_CONTRACT_KEY")
            caps = item.get("capabilities")
            if not isinstance(caps, dict):
                raise RegistryError("CAPABILITIES_INVALID")
            for name in CAPABILITIES:
                value = caps.get(name, UNKNOWN)
                if not (type(value) is bool or value == UNKNOWN):
                    raise RegistryError(f"CAPABILITY_VALUE_INVALID:{name}")
                if value != UNKNOWN and not self._has_evidence(item, name, value):
                    raise RegistryError(f"CAPABILITY_EVIDENCE_MISSING:{name}")
            self._records[key] = dict(item)

    @staticmethod
    def _key(item: Mapping[str, Any]) -> tuple[str, ...]:
        names = ("venue", "product", "endpoint", "channel", "message_type", "field_path", "protocol_version")
        values = []
        for name in names:
            value = item.get(name)
            if not isinstance(value, str) or not value.strip():
                raise RegistryError(f"CONTRACT_SCOPE_MISSING:{name}")
            values.append(value.strip())
        return tuple(values)

    @staticmethod
    def _has_evidence(
        item: Mapping[str, Any], capability: str | None = None, expected_value: bool = True
    ) -> bool:
        evidence = item.get("evidence")
        return bool(
            isinstance(evidence, list)
            and any(
                isinstance(row, dict)
                and isinstance(row.get("primary_source_url"), str)
                and row["primary_source_url"].startswith("https://")
                and row.get("evidence_class") == "primary_protocol_contract"
                and isinstance(row.get("evidence_ref"), str)
                and row["evidence_ref"].strip()
                and (
                    capability is None
                    or (
                        isinstance(row.get("capability_claims"), dict)
                        and row["capability_claims"].get(capability) is expected_value
                    )
                )
                and all(
                    isinstance(row.get(field), str)
                    and len(row[field]) == 64
                    and all(ch in "0123456789abcdef" for ch in row[field])
                    for field in ("source_snapshot_sha256", "excerpt_sha256")
                )
                for row in evidence
            )
        )

    @classmethod
    def load(cls, path: str | Path) -> "SequenceSemanticsRegistryV1":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError("REGISTRY_UNREADABLE") from exc
        if not isinstance(payload, dict):
            raise RegistryError("REGISTRY_ROOT_INVALID")
        return cls(payload)

    def resolve(self, *, venue: str, product: str, endpoint: str, channel: str,
                message_type: str, field_path: str, protocol_version: str) -> dict[str, Any] | None:
        key = (venue, product, endpoint, channel, message_type, field_path, protocol_version)
        record = self._records.get(key)
        return dict(record) if record is not None else None

    def capability(self, contract: Mapping[str, Any] | None, name: str) -> bool | str:
        if name not in CAPABILITIES:
            raise RegistryError("UNKNOWN_CAPABILITY")
        if contract is None:
            return UNKNOWN
        return contract.get("capabilities", {}).get(name, UNKNOWN)

    def may_claim(self, contract: Mapping[str, Any] | None, name: str) -> bool:
        return self.capability(contract, name) is True and self._has_evidence(contract or {}, name, True)

    def classify_duplicate(self, contract: Mapping[str, Any] | None, *,
                           first_payload_sha256: str, current_payload_sha256: str) -> str:
        if first_payload_sha256 == current_payload_sha256:
            return "EXACT_PAYLOAD_REPLAY"
        if self.may_claim(contract, "event_identity_unique"):
            return "CONFLICTING_DOCUMENTED_IDENTITY"
        return "AMBIGUOUS_DUPLICATE"

    def classify_numeric_gap(self, contract: Mapping[str, Any] | None, *,
                             previous: int, current: int) -> str:
        if type(previous) is not int or type(current) is not int:
            return "INVALID_NUMERIC_INPUT"
        if current <= previous:
            return "NOT_A_FORWARD_GAP"
        if (self.may_claim(contract, "contiguous_within_scope")
                and self.may_claim(contract, "gap_detectable")):
            return "MISSING_EVENT" if current > previous + 1 else "CONTIGUOUS"
        return "NOT_INFERABLE_FROM_NUMERIC_GAP"


def load_default_registry() -> SequenceSemanticsRegistryV1:
    return SequenceSemanticsRegistryV1.load(
        Path(__file__).resolve().parents[1] / "docs/protocol/sequence_semantics_registry_v1.json"
    )
