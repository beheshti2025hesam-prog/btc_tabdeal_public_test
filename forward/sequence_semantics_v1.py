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
    contract_key: tuple[tuple[str, str], ...]
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
    review_revision: str
    status: str

    @property
    def verified(self) -> bool:
        return (
            self.status == "VERIFIED"
            and _sha256(self.registry_sha256)
            and _sha256(self.source_content_sha256)
            and bool(self.record_id and self.contract_key and self.field_path and self.scope and self.review_revision)
        )

    @property
    def supports_scalar_sequence_integrity(self) -> bool:
        return (
            self.verified
            and self.semantic_class == "ORDERED_EVENT_SEQUENCE"
            and self.ordered
        )


@dataclass(frozen=True)
class SequenceEventV2:
    sequence: int | None
    status: str
    reason: str | None = None
    diagnostic: dict[str, Any] | None = None


class SequenceIntegrityV2:
    """Apply only a verified scalar ordered-sequence contract.

    Book ranges, timestamps, trade identifiers without ordering guarantees,
    and opaque fields are intentionally rejected by this scalar state machine.
    """

    def __init__(self, capabilities: SequenceCapabilitiesV1 | None, *, max_records: int = 100_000):
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self.capabilities = capabilities
        self.max_records = max_records
        self.last_sequence: int | None = None
        self._scope: tuple[tuple[str, str], ...] | None = None
        self._identity_hashes: dict[int, str] = {}
        self._raw_hashes: set[str] = set()
        self._count = 0

    @staticmethod
    def _digest(record: dict[str, Any]) -> str:
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def observe(self, record: dict[str, Any]) -> SequenceEventV2:
        caps = self.capabilities
        if caps is None or not caps.supports_scalar_sequence_integrity:
            return SequenceEventV2(None, "BLOCKED", "SEQUENCE_SEMANTICS_UNVERIFIED")
        if not isinstance(record, dict):
            return SequenceEventV2(None, "BLOCKED", "SEQUENCE_RECORD_INVALID")
        if record.get("sequence_contract_key") != dict(caps.contract_key):
            return SequenceEventV2(None, "BLOCKED", "SEQUENCE_CONTRACT_KEY_MISMATCH")

        scope_values: list[tuple[str, str]] = []
        for field_name in caps.scope:
            value = record.get(field_name)
            if value is None or isinstance(value, (dict, list)):
                return SequenceEventV2(None, "BLOCKED", "SEQUENCE_SCOPE_FIELD_MISSING")
            scope_values.append((field_name, str(value)))
        scope = tuple(scope_values)
        if self._scope is None:
            self._scope = scope
        elif scope != self._scope:
            return SequenceEventV2(None, "BLOCKED", "SEQUENCE_SCOPE_CHANGED")

        value: Any = record
        try:
            for part in caps.field_path.split("."):
                value = value[part]
        except (KeyError, TypeError):
            return SequenceEventV2(None, "BLOCKED", "SEQUENCE_FIELD_MISSING")
        if type(value) is not int or value < 0:
            return SequenceEventV2(None, "BLOCKED", "SEQUENCE_VALUE_MUST_BE_NONNEGATIVE_INTEGER")
        seq = value

        raw_hash = record.get("raw_payload_sha256")
        if raw_hash is not None and not _sha256(raw_hash):
            return SequenceEventV2(seq, "BLOCKED", "RAW_PAYLOAD_HASH_INVALID")
        if caps.exact_payload_replay_only and _sha256(raw_hash) and raw_hash in self._raw_hashes:
            return SequenceEventV2(seq, "IDEMPOTENT_DUPLICATE", "EXACT_RAW_PAYLOAD_REPLAY")

        payload_hash = raw_hash if _sha256(raw_hash) else self._digest(record)
        if caps.event_identity and seq in self._identity_hashes:
            if self._identity_hashes[seq] == payload_hash:
                return SequenceEventV2(seq, "IDEMPOTENT_DUPLICATE", "IDENTICAL_EVENT_IDENTITY")
            return SequenceEventV2(
                seq, "REJECT_STREAM", "CONFLICTING_DUPLICATE_IDENTITY",
                {"previous_payload_sha256": self._identity_hashes[seq],
                 "conflicting_payload_sha256": payload_hash},
            )

        if self.last_sequence is not None:
            if seq < self.last_sequence:
                return SequenceEventV2(seq, "ANOMALY", "OUT_OF_ORDER_SEQUENCE")
            if caps.contiguous and caps.gap_detection and seq > self.last_sequence + 1:
                return SequenceEventV2(
                    seq, "REJECT_STREAM", "MISSING_EVENT",
                    {"last_sequence": self.last_sequence, "next_sequence": seq},
                )

        if self._count >= self.max_records:
            return SequenceEventV2(seq, "REJECT_STREAM", "SEQUENCE_STATE_BOUND_EXCEEDED",
                                   {"max_records": self.max_records})
        self._count += 1
        if caps.event_identity:
            self._identity_hashes[seq] = payload_hash
        if caps.exact_payload_replay_only and _sha256(raw_hash):
            self._raw_hashes.add(raw_hash)
        if self.last_sequence is None or seq > self.last_sequence:
            self.last_sequence = seq
        return SequenceEventV2(seq, "ACCEPTED")

    def reset_for_reconnect(self) -> None:
        """Start a new session epoch; never compare IDs across reconnects by default."""
        self.last_sequence = None
        self._scope = None
        self._identity_hashes.clear()
        self._raw_hashes.clear()
        self._count = 0


DEFAULT_REGISTRY_SHA256 = "d4ca2bf1843fc32ac4bd0800b02d9e435083e74de48010c4b08294d255fee479"
DEFAULT_TABDEAL_TRADE_RECORD_ID = "tabdeal_fapi_broadcast_trade_sequence_v1"
TABDEAL_TRADE_SEQUENCE_KEY = {
    "venue": "tabdeal",
    "product": "fapi_margin",
    "endpoint": "wss://api1.tabdeal.org/special_margin/broadcast/",
    "channel": "raw_text_symbol_subscription",
    "message_type": "trade_envelope",
    "field_path": "trade.sequence",
    "protocol_version": "unknown",
}


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
        self._keys: set[tuple[str, ...]] = set()
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
            key_tuple = tuple(key[name] for name in (
                "venue", "product", "endpoint", "channel", "message_type",
                "field_path", "protocol_version"
            ))
            if key_tuple in self._keys:
                raise SequenceSemanticsError("SEQUENCE_REGISTRY_DUPLICATE_SCOPE_KEY")
            self._keys.add(key_tuple)
            scope = record.get("scope")
            if (not isinstance(scope, list) or not scope
                    or any(not isinstance(item, str) or not item.strip() for item in scope)
                    or len(set(scope)) != len(scope)):
                raise SequenceSemanticsError("SEQUENCE_REGISTRY_SCOPE_INVALID")
            claims = record.get("claims")
            capabilities = record.get("capabilities")
            if not isinstance(claims, dict) or not isinstance(capabilities, dict):
                raise SequenceSemanticsError("SEQUENCE_REGISTRY_CAPABILITIES_INVALID")
            if any(type(value) is not bool for value in capabilities.values()):
                raise SequenceSemanticsError("SEQUENCE_REGISTRY_CAPABILITY_TYPE_INVALID")
            if record.get("status") not in {
                "UNKNOWN", "SOURCE_REVIEWED_UNPINNED", "SOURCE_REVIEW_REQUIRED",
                "VERIFIED", "RETIRED"
            }:
                raise SequenceSemanticsError("SEQUENCE_REGISTRY_STATUS_INVALID")
            if record.get("status") == "VERIFIED":
                evidence = record.get("source_evidence")
                if not isinstance(evidence, dict) or not _sha256(evidence.get("source_content_sha256")):
                    raise SequenceSemanticsError("VERIFIED_RECORD_SOURCE_HASH_MISSING")
                if evidence.get("source_kind") != "primary":
                    raise SequenceSemanticsError("VERIFIED_RECORD_PRIMARY_SOURCE_REQUIRED")
                if not isinstance(record.get("independent_review_revision"), str) or not record["independent_review_revision"].strip():
                    raise SequenceSemanticsError("VERIFIED_RECORD_REVIEW_REVISION_MISSING")
                if not isinstance(evidence.get("url"), str) or not evidence["url"].startswith("https://"):
                    raise SequenceSemanticsError("VERIFIED_RECORD_PRIMARY_URL_MISSING")
                if not isinstance(record.get("normalized_field_path"), str) or not record["normalized_field_path"].strip():
                    raise SequenceSemanticsError("VERIFIED_RECORD_NORMALIZED_FIELD_PATH_MISSING")
                if record.get("semantic_class") == "ORDERED_EVENT_SEQUENCE" and claims.get("ordered") is not True:
                    raise SequenceSemanticsError("VERIFIED_ORDERED_SEQUENCE_CLAIM_MISSING")
                if capabilities.get("event_identity") is True and claims.get("unique") is not True:
                    raise SequenceSemanticsError("EVENT_IDENTITY_REQUIRES_UNIQUENESS_CLAIM")
                if capabilities.get("contiguous_gap_detection") is True and claims.get("contiguous") is not True:
                    raise SequenceSemanticsError("GAP_DETECTION_REQUIRES_CONTIGUITY_CLAIM")
                if capabilities.get("book_update_range") is True and record.get("semantic_class") != "BOOK_UPDATE_RANGE":
                    raise SequenceSemanticsError("BOOK_RANGE_CAPABILITY_SCOPE_INVALID")
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

    @classmethod
    def load_default(cls) -> "SequenceSemanticsRegistryV1":
        path = Path(__file__).with_name("sequence_semantics_registry_v1.json")
        return cls.load(path, expected_sha256=DEFAULT_REGISTRY_SHA256)

    def resolve_tabdeal_trade_sequence(self) -> SequenceCapabilitiesV1:
        return self.resolve(
            DEFAULT_TABDEAL_TRADE_RECORD_ID,
            expected_key=TABDEAL_TRADE_SEQUENCE_KEY,
        )

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
            contract_key=tuple(sorted(expected_key.items())),
            semantic_class=record["semantic_class"],
            field_path=record.get("normalized_field_path", record["key"]["field_path"]),
            scope=tuple(record.get("scope", ())),
            ordered=record.get("claims", {}).get("ordered") is True,
            event_identity=caps.get("event_identity") is True,
            contiguous=record.get("claims", {}).get("contiguous") is True,
            gap_detection=caps.get("contiguous_gap_detection") is True,
            snapshot_bootstrap=caps.get("snapshot_bootstrap") is True,
            exact_payload_replay_only=caps.get("exact_payload_replay_only") is True,
            registry_sha256=self.registry_sha256,
            source_content_sha256=evidence["source_content_sha256"],
            review_revision=record["independent_review_revision"],
            status=record["status"],
        )
