"""Hash-pinned, scope-specific sequence capability registry.

This module is deliberately conservative: a field name or numeric value is not
sequence evidence. Unknown capabilities remain disabled. It does not open
network connections or enable collection/trading.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCOPE_FIELDS = (
    "venue", "product", "transport", "endpoint", "channel_or_topic",
    "message_type", "field_path", "protocol_version",
)
_CAPABILITIES = (
    "unique", "monotonic", "contiguous", "ordered",
    "comparable_across_reconnect", "comparable_across_symbols",
    "comparable_across_channels", "gap_detection_supported",
    "duplicate_identity_supported",
)


class RegistryError(ValueError):
    """Registry is invalid or does not prove the requested capability."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RegistryError("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _strict_json(raw: bytes) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                RegistryError("NON_FINITE_JSON_NUMBER")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError("INVALID_JSON") from exc


@dataclass(frozen=True)
class VerifiedSequenceContract:
    registry_revision: str
    semantic_class: str
    scope: Mapping[str, str]
    capabilities: Mapping[str, bool | str]
    status: str

    @property
    def gap_detection_authorized(self) -> bool:
        return (
            self.status == "verified"
            and self.capabilities.get("gap_detection_supported") is True
            and self.capabilities.get("contiguous") is True
            and self.capabilities.get("ordered") is True
        )


def load_verified_contract(
    registry_path: str | Path,
    lock_path: str | Path,
    expected_scope: Mapping[str, str],
) -> VerifiedSequenceContract:
    """Load only a SHA-256-pinned record matching every scope dimension.

    The separate lock detects registry-only edits; when both files live in the
    same repository, the lock itself is protected by repository review and
    commit controls, not by cryptographic independence. This validates local
    integrity, not the truth of the cited source. Positive capabilities
    additionally require primary-source snapshot hashes and evidence metadata.
    """
    raw = Path(registry_path).read_bytes()
    lock_raw = Path(lock_path).read_bytes()
    lock = _strict_json(lock_raw)
    registry = _strict_json(raw)

    if not isinstance(lock, dict) or lock.get("schema") != "hes_sequence_registry_lock_v1":
        raise RegistryError("LOCK_SCHEMA_INVALID")
    pinned = lock.get("registry_sha256")
    if not isinstance(pinned, str) or not _SHA256.fullmatch(pinned):
        raise RegistryError("LOCK_DIGEST_INVALID")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != pinned:
        raise RegistryError("REGISTRY_DIGEST_MISMATCH")
    if not isinstance(registry, dict) or registry.get("schema") != "hes_sequence_capability_registry_v1":
        raise RegistryError("REGISTRY_SCHEMA_INVALID")
    revision = registry.get("registry_revision")
    if not isinstance(revision, str) or not revision.strip() or revision != lock.get("registry_revision"):
        raise RegistryError("REGISTRY_REVISION_MISMATCH")
    records = registry.get("records")
    if not isinstance(records, list):
        raise RegistryError("RECORDS_INVALID")

    if set(expected_scope) != set(_SCOPE_FIELDS) or any(
        not isinstance(expected_scope.get(key), str) or not expected_scope[key].strip()
        for key in _SCOPE_FIELDS
    ):
        raise RegistryError("EXPECTED_SCOPE_INCOMPLETE")

    matches = [
        record for record in records
        if isinstance(record, dict)
        and all(record.get(key) == expected_scope[key] for key in _SCOPE_FIELDS)
    ]
    if len(matches) != 1:
        raise RegistryError("SCOPE_NOT_UNIQUELY_REGISTERED")
    record = matches[0]

    semantic_class = record.get("semantic_class")
    status = record.get("status")
    claims = record.get("claims")
    if semantic_class not in {
        "opaque_id", "event_id", "message_sequence", "book_update_range",
        "timestamp", "cursor", "unknown",
    }:
        raise RegistryError("SEMANTIC_CLASS_INVALID")
    if status not in {"active-but-conservative", "verified", "superseded"}:
        raise RegistryError("STATUS_INVALID")
    if not isinstance(claims, dict) or any(key not in claims for key in _CAPABILITIES):
        raise RegistryError("CAPABILITIES_INCOMPLETE")
    for key in _CAPABILITIES:
        value = claims[key]
        if type(value) is not bool and value != "unknown":
            raise RegistryError("CAPABILITY_VALUE_INVALID")

    if status != "verified" and any(claims[key] is True for key in _CAPABILITIES):
        raise RegistryError("UNVERIFIED_STATUS_CANNOT_GRANT_CAPABILITY")

    if status == "verified":
        evidence = record.get("source_evidence")
        if not isinstance(evidence, list) or not evidence:
            raise RegistryError("POSITIVE_CLAIM_WITHOUT_SOURCE")
        for item in evidence:
            if not isinstance(item, dict) or item.get("source_kind") != "primary":
                raise RegistryError("NON_PRIMARY_EVIDENCE")
            if not isinstance(item.get("url"), str) or not item["url"].startswith("https://"):
                raise RegistryError("SOURCE_URL_INVALID")
            if not isinstance(item.get("retrieved_at"), str) or not item["retrieved_at"].strip():
                raise RegistryError("SOURCE_RETRIEVAL_METADATA_MISSING")
            source_digest = item.get("source_content_sha256")
            if not isinstance(source_digest, str) or not _SHA256.fullmatch(source_digest):
                raise RegistryError("SOURCE_SNAPSHOT_NOT_HASH_PINNED")
            if not isinstance(item.get("evidence_excerpt"), str) or not item["evidence_excerpt"].strip():
                raise RegistryError("SOURCE_EXCERPT_MISSING")
        if semantic_class == "unknown" and any(claims[k] is True for k in _CAPABILITIES):
            raise RegistryError("UNKNOWN_SEMANTICS_CANNOT_GRANT_CAPABILITY")

    return VerifiedSequenceContract(
        registry_revision=revision,
        semantic_class=semantic_class,
        scope={key: record[key] for key in _SCOPE_FIELDS},
        capabilities={key: claims[key] for key in _CAPABILITIES},
        status=status,
    )
