"""Fail-closed verification for detached HES source-retrieval attestations.

The trust root MUST be injected by protected runtime configuration, never read
from the PR-controlled registry/lock. This module verifies a signed statement;
it does not itself retrieve URLs or prove that a signer used a trustworthy
retrieval process. That guarantee belongs to the separately governed attestor.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "schema_version",
    "snapshot_sha256",
    "requested_url",
    "final_url",
    "redirect_chain",
    "retrieved_at_utc",
    "retrieval_tool",
    "retrieval_tool_version",
    "source_context",
    "signer_key_id",
}
SCHEMA_VERSION = "hes-source-attestation-v1"


class AttestationError(ValueError):
    """Raised when attestation verification must fail closed."""


def _canonical_payload(attestation: dict[str, Any]) -> bytes:
    payload = {k: v for k, v in attestation.items() if k != "signature"}
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def verify_attestation(
    *,
    snapshot_path: str | Path,
    attestation_path: str | Path,
    expected_context: dict[str, Any],
    trusted_public_key_b64: str | None = None,
) -> dict[str, Any]:
    """Verify signed attestation and exact raw snapshot bytes; raise on any gap.

    Public key defaults to HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64, which must
    come from protected environment/secret configuration external to the PR.
    Ed25519 verification requires the 'cryptography' package.
    """
    key_b64 = trusted_public_key_b64 or os.environ.get(
        "HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64"
    )
    if not key_b64:
        raise AttestationError("BLOCK: external trust root is not configured")

    try:
        att = json.loads(Path(attestation_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise AttestationError("BLOCK: unreadable attestation") from exc
    if not isinstance(att, dict) or not REQUIRED_FIELDS | {"signature"} <= set(att):
        raise AttestationError("BLOCK: required attestation fields missing")
    if att["schema_version"] != SCHEMA_VERSION:
        raise AttestationError("BLOCK: unsupported attestation schema")
    if not isinstance(att["redirect_chain"], list) or not att["redirect_chain"]:
        raise AttestationError("BLOCK: redirect chain must include final response")
    if not isinstance(att["source_context"], dict):
        raise AttestationError("BLOCK: source context must be an object")
    for key, expected in expected_context.items():
        if att["source_context"].get(key) != expected:
            raise AttestationError(f"BLOCK: source context mismatch for {key}")

    try:
        snapshot = Path(snapshot_path).read_bytes()
        actual_digest = hashlib.sha256(snapshot).hexdigest()
        declared_digest = att["snapshot_sha256"]
        if not isinstance(declared_digest, str) or actual_digest != declared_digest:
            raise AttestationError("BLOCK: snapshot SHA-256 mismatch")
        public_key = base64.b64decode(key_b64, validate=True)
        signature = base64.b64decode(att["signature"], validate=True)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, _canonical_payload(att)
        )
    except AttestationError:
        raise
    except Exception as exc:
        raise AttestationError("BLOCK: invalid key, signature, or attestation encoding") from exc

    return {
        "verified": True,
        "snapshot_sha256": actual_digest,
        "signer_key_id": att["signer_key_id"],
        "source_context": att["source_context"],
    }
