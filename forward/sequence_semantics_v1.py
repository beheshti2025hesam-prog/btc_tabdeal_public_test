"""Capability-driven exchange sequence semantics registry (v1).

Field names are not contracts. Positive capabilities require an exact,
scope-bound registry record and a pinned primary-source content hash.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


class SequenceSemanticsError(ValueError):
    """The requested sequence contract is missing, ambiguous, or unverified."""


def _sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value.lower())
    )


@dataclass(frozen=True)
class SequenceCapabilitiesV1:
    record_id: str
    semantic_class: str
    field_path: str
    scope: tuple[str, ...]
    ordered: bool
    event_identity: bool
    contiguous: bool
    gap_detection: bool
    snapshot_bootstrap: bool
    exact_payload_replay_only: bool
    registry_sha256: str
    source_content_sha256: str
    status: str

    @property
    def verified(self) -> bool:
        return (
            self.status == "VERIFIED"
            and _sha256(self.registry_sha256)
            and _sha256(self.source_content_sha256)
            and bool(self.record_id and self.field_path and self.scope)
        )

    @property
    def supports_scalar_sequence_integrity(self) -> bool:
        return (
            self.verified
            and self.semantic_class == "ORDERED_EVENT_SEQUENCE"
            and self.ordered
        )


class SequenceSemanticsRegistryV1:
    SCHEMA = "hes_sequence_semantics_registry_v1"

    def __init__(self, payload: dict[str, Any], *, raw_sha256: str):
        if payload.get("schema") != self.SCHEMA:
            raise SequenceSemanticsError("SEQUENCE_REGISTRY_SCHEMA_INVALID")
        records = payload.get("records")
        if not isinstance(records, list):
            raise SequenceSemanticsError("SEQUENCE_REGISTRY_RECORDS_INVALID")
        if not _sha256(raw_sha256):
            raise SequenceSemanticsError("SEQUENCE_REGISTRY_HASH_INVALID")
        self.registry_sha256 = raw_sha256
        self._records: dict[str, dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, dict):
                raise SequenceSemanticsError("SEQUENCE_REGISTRY_RECORD_INVALID")
            record_id = record.get("record_id")
            if not isinstance(record_id, str) or not record_id.strip() or record_id in self._records:
                raise SequenceSemanticsError("SEQUENCE_REGISTRY_RECORD_ID_INVALID")
            key = record.get("key")
            if not isinstance(key, dict) or any(
                not isinstance(key.get(name), str) or not key[name].strip()
                for name in ("venue", "product", "endpoint", "channel", "message_type", "field_path", "protocol_version")
            ):
                raise SequenceSemanticsError("SEQUENCE_REGISTRY_KEY_INVALID")
            claims = record.get("claims")
            capabilities = record.get("capabilities")
            if not isinstance(claims, dict) or not isinstance(capabilities, dict):
                raise SequenceSemanticsError("SEQUENCE_REGISTRY_CAPABILITIES_INVALID")
            if record.get("status") == "VERIFIED":
                evidence = record.get("source_evidence")
                if not isinstance(evidence, dict) or not _sha256(evidence.get("source_content_sha256")):
                    raise SequenceSemanticsError("VERIFIED_RECORD_SOURCE_HASH_MISSING")
                if evidence.get("source_kind") != "primary":
                    raise SequenceSemanticsError("VERIFIED_RECORD_PRIMARY_SOURCE_REQUIRED")
            self._records[record_id] = record

    @classmethod
    def load(cls, path: str | Path, *, expected_sha256: str) -> "SequenceSemanticsRegistryV1":
        if not _sha256(expected_sha256):
            raise SequenceSemanticsError("SEQUENCE_REGISTRY_EXPECTED_HASH_REQUIRED")
        raw = Path(path).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected_sha256:
            raise SequenceSemanticsError("SEQUENCE_REGISTRY_HASH_MISMATCH")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SequenceSemanticsError("SEQUENCE_REGISTRY_JSON_INVALID") from exc
        return cls(payload, raw_sha256=actual)

    def inspect(self, record_id: str) -> dict[str, Any]:
        try:
            return json.loads(json.dumps(self._records[record_id]))
        except KeyError as exc:
            raise SequenceSemanticsError("SEQUENCE_REGISTRY_RECORD_NOT_FOUND") from exc

    def resolve(self, record_id: str, *, expected_key: dict[str, str]) -> SequenceCapabilitiesV1:
        record = self.inspect(record_id)
        if record.get("status") != "VERIFIED":
            raise SequenceSemanticsError("SEQUENCE_SEMANTICS_NOT_VERIFIED")
        if record.get("key") != expected_key:
            raise SequenceSemanticsError("SEQUENCE_REGISTRY_SCOPE_MISMATCH")
        evidence = record.get("source_evidence", {})
        caps = record.get("capabilities", {})
        if evidence.get("source_kind") != "primary" or not _sha256(evidence.get("source_content_sha256")):
            raise SequenceSemanticsError("SEQUENCE_PRIMARY_EVIDENCE_NOT_PINNED")
        if record.get("semantic_class") != "ORDERED_EVENT_SEQUENCE":
            raise SequenceSemanticsError("SEQUENCE_FIELD_IS_NOT_SCALAR_ORDERED_SEQUENCE")
        return SequenceCapabilitiesV1(
            record_id=record_id,
            semantic_class=record["semantic_class"],
            field_path=record["key"]["field_path"],
            scope=tuple(record.get("scope", ())),
            ordered=record.get("claims", {}).get("ordered") is True,
            event_identity=caps.get("event_identity") is True,
            contiguous=record.get("claims", {}).get("contiguous") is True,
            gap_detection=caps.get("contiguous_gap_detection") is True,
            snapshot_bootstrap=caps.get("snapshot_bootstrap") is True,
            exact_payload_replay_only=caps.get("exact_payload_replay_only") is True,
            registry_sha256=self.registry_sha256,
            source_content_sha256=evidence["source_content_sha256"],
            status=record["status"],
        )
