"""Versioned executor/validator/signer contract for evidence attestations.

The trusted public key must be provisioned outside the pull request/repository
(e.g. protected environment secret or independently managed trust store).
No private key is loaded by this module.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED = {
    "schema", "artifact_path", "artifact_sha256", "artifact_bytes",
    "commit_sha", "signer_key_id", "signature_algorithm",
}
_SIGNATURE_FIELDS = {"signature"}


class AttestationError(ValueError):
    """Raised when an attestation fails closed validation."""


def canonical_payload(attestation: dict[str, Any]) -> bytes:
    """Return deterministic bytes over the exact signed fields."""
    if not isinstance(attestation, dict):
        raise AttestationError("attestation must be an object")
    missing = (_REQUIRED | _SIGNATURE_FIELDS) - set(attestation)
    extra = set(attestation) - (_REQUIRED | _SIGNATURE_FIELDS)
    if missing:
        raise AttestationError(f"missing fields: {','.join(sorted(missing))}")
    if extra:
        raise AttestationError(f"unexpected fields: {','.join(sorted(extra))}")
    if attestation["schema"] != "hes.evidence_attestation.v1":
        raise AttestationError("unsupported schema")
    if not isinstance(attestation["artifact_path"], str) or not attestation["artifact_path"].strip():
        raise AttestationError("artifact_path must be a non-empty string")
    if not isinstance(attestation["artifact_sha256"], str) or not _SHA256_RE.fullmatch(attestation["artifact_sha256"]):
        raise AttestationError("artifact_sha256 must be lowercase SHA-256 hex")
    if type(attestation["artifact_bytes"]) is not int or attestation["artifact_bytes"] < 0:
        raise AttestationError("artifact_bytes must be a non-negative integer")
    if not isinstance(attestation["commit_sha"], str) or not _COMMIT_RE.fullmatch(attestation["commit_sha"]):
        raise AttestationError("commit_sha must be a full lowercase Git SHA")
    if not isinstance(attestation["signer_key_id"], str) or not attestation["signer_key_id"].strip():
        raise AttestationError("signer_key_id must be non-empty")
    if attestation["signature_algorithm"] != "Ed25519":
        raise AttestationError("signature_algorithm must be Ed25519")
    signed = {key: attestation[key] for key in sorted(_REQUIRED)}
    return json.dumps(signed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify_attestation(
    attestation: dict[str, Any],
    artifact_bytes: bytes,
    trusted_key_id: str,
    trusted_public_key: bytes,
) -> bool:
    """Verify schema, external key identity, artifact hash/size, and Ed25519 signature."""
    canonical = canonical_payload(attestation)
    if attestation["signer_key_id"] != trusted_key_id:
        raise AttestationError("untrusted signer_key_id")
    if not isinstance(artifact_bytes, bytes):
        raise AttestationError("artifact must be bytes")
    if len(artifact_bytes) != attestation["artifact_bytes"]:
        raise AttestationError("artifact byte length mismatch")
    if hashlib.sha256(artifact_bytes).hexdigest() != attestation["artifact_sha256"]:
        raise AttestationError("artifact SHA-256 mismatch")
    try:
        signature = base64.b64decode(attestation["signature"], validate=True)
    except (ValueError, TypeError) as exc:
        raise AttestationError("signature must be valid base64") from exc
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(trusted_public_key).verify(signature, canonical)
    except Exception as exc:
        raise AttestationError("Ed25519 signature verification failed") from exc
    return True
