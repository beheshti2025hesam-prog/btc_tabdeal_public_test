"""Fail-closed verification of independently reviewed source evidence."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Any

# Release-controlled trust anchor. Deliberately unset until reviewed and pinned.
PINNED_SOURCE_EVIDENCE_REGISTRY_SHA256 = ""

class SourceEvidenceRegistryError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)

def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise SourceEvidenceRegistryError("REGISTRY_DUPLICATE_JSON_KEY")
        out[key] = value
    return out

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

class SourceEvidenceRegistryV1:
    """Verify registry pin, independent-review metadata, scope, and artifact bytes."""
    def __init__(self, path: Path, entries: dict[str, dict[str, Any]]):
        self.path = path
        self.root = path.parent.resolve()
        self.entries = entries

    @classmethod
    def load(cls, registry_path: str | Path) -> "SourceEvidenceRegistryV1":
        pin = PINNED_SOURCE_EVIDENCE_REGISTRY_SHA256
        if not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{64}", pin):
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REGISTRY_PIN_UNSET")
        path = Path(registry_path)
        if path.is_symlink() or not path.is_file():
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REGISTRY_FILE_UNAVAILABLE")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REGISTRY_READ_FAILED") from exc
        if _sha256(raw) != pin:
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REGISTRY_PIN_MISMATCH")
        try:
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except SourceEvidenceRegistryError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REGISTRY_INVALID_JSON") from exc
        if not isinstance(data, dict) or data.get("schema") != "hes_source_evidence_registry_v1":
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REGISTRY_SCHEMA_INVALID")
        if data.get("status") != "REVIEWED_PINNED":
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REGISTRY_NOT_REVIEWED")
        items = data.get("entries")
        if not isinstance(items, list):
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REGISTRY_ENTRIES_INVALID")
        entries = {}
        for item in items:
            if not isinstance(item, dict):
                raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_ENTRY_INVALID")
            ref = item.get("evidence_ref")
            if not isinstance(ref, str) or not ref.strip() or ref in entries:
                raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REF_INVALID_OR_DUPLICATE")
            if item.get("review_status") != "INDEPENDENTLY_REVIEWED":
                raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_NOT_INDEPENDENTLY_REVIEWED")
            for key, code in (
                ("review_record_ref", "SOURCE_EVIDENCE_REVIEW_RECORD_MISSING"),
                ("evidence_path", "SOURCE_EVIDENCE_ARTIFACT_PATH_MISSING"),
                ("evidence_type", "SOURCE_EVIDENCE_TYPE_MISSING"),
                ("source_scope", "SOURCE_EVIDENCE_SCOPE_MISSING"),
            ):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    raise SourceEvidenceRegistryError(code)
            if not isinstance(item.get("evidence_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["evidence_sha256"]):
                raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_ARTIFACT_DIGEST_INVALID")
            entries[ref] = item
        return cls(path, entries)

    def resolve(self, ref: str, *, evidence_type: str, source_scope: str) -> dict[str, Any]:
        if not isinstance(ref, str) or not ref.strip():
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REF_MISSING")
        item = self.entries.get(ref)
        if item is None:
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_REF_NOT_REGISTERED")
        if item["evidence_type"] != evidence_type:
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_TYPE_MISMATCH")
        if item["source_scope"] != source_scope:
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_SCOPE_MISMATCH")
        relative = Path(item["evidence_path"])
        if relative.is_absolute():
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_PATH_OUTSIDE_ROOT")
        candidate = self.root / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_ARTIFACT_UNAVAILABLE")
        try:
            candidate.resolve(strict=True).relative_to(self.root)
            artifact = candidate.read_bytes()
        except (OSError, ValueError) as exc:
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_PATH_OUTSIDE_ROOT") from exc
        if _sha256(artifact) != item["evidence_sha256"]:
            raise SourceEvidenceRegistryError("SOURCE_EVIDENCE_ARTIFACT_DIGEST_MISMATCH")
        return dict(item)



def verify_source_evidence_bundle(
    registry_path: str | Path,
    *,
    sequence_contract_ref: str,
    source_completeness_ref: str,
    source_ordering_ref: str,
    source_scope: str,
) -> SourceEvidenceRegistryV1:
    """Verify all three required proof classes against one pinned registry."""
    registry = SourceEvidenceRegistryV1.load(registry_path)
    registry.resolve(sequence_contract_ref, evidence_type="sequence_contract", source_scope=source_scope)
    registry.resolve(source_completeness_ref, evidence_type="source_completeness", source_scope=source_scope)
    registry.resolve(source_ordering_ref, evidence_type="source_ordering", source_scope=source_scope)
    return registry
