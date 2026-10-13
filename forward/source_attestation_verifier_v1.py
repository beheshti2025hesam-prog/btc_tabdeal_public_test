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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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

REQUIRED_CONTEXT_FIELDS = {
    "venue",
    "product",
    "endpoint",
    "channel",
    "message_type",
    "field",
    "protocol_version",
    "reviewed_commit_sha",
    "contract_version",
}
MAX_ATTESTATION_AGE = timedelta(hours=24)
ALLOWED_FUTURE_SKEW = timedelta(minutes=5)


class AttestationError(ValueError):
    """Raised when attestation verification must fail closed."""


def _canonical_payload(attestation: dict[str, Any]) -> bytes:
    payload = {k: v for k, v in attestation.items() if k != "signature"}
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _validate_https_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False


def _validate_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        return parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0
    except ValueError:
        return False


def verify_attestation(
    *,
    snapshot_path: str | Path,
    attestation_path: str | Path,
    expected_context: dict[str, Any],
    now_utc: datetime | None = None,
    max_age: timedelta = MAX_ATTESTATION_AGE,
    allowed_future_skew: timedelta = ALLOWED_FUTURE_SKEW,
) -> dict[str, Any]:
    """Verify signed attestation and exact raw snapshot bytes; raise on any gap.

    Public key defaults to HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64, which must
    come from protected environment configuration external to the PR.
    Ed25519 verification requires the 'cryptography' package.
    """
    # Never accept the trust root as a function argument: callers could pass
    # a key bundled with the untrusted attestation. Inject only via protected
    # runtime configuration managed outside PR-writable files.
    key_b64 = os.environ.get("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64")
    configured_key_id = os.environ.get("HES_SOURCE_ATTESTATION_KEY_ID")
    if not key_b64 or not configured_key_id:
        raise AttestationError("BLOCK: external trust root or key identity is not configured")

    try:
        att = json.loads(Path(attestation_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise AttestationError("BLOCK: unreadable attestation") from exc
    if not isinstance(att, dict) or not REQUIRED_FIELDS | {"signature"} <= set(att):
        raise AttestationError("BLOCK: required attestation fields missing")
    if att["schema_version"] != SCHEMA_VERSION:
        raise AttestationError("BLOCK: unsupported attestation schema")
    if not _validate_https_url(att["requested_url"]) or not _validate_https_url(att["final_url"]):
        raise AttestationError("BLOCK: source URLs must be valid HTTPS URLs without credentials")
    if not _validate_utc_timestamp(att["retrieved_at_utc"]):
        raise AttestationError("BLOCK: retrieval timestamp must be ISO-8601 UTC ending in Z")
    if max_age < timedelta(0) or allowed_future_skew < timedelta(0):
        raise ValueError("max_age and allowed_future_skew must be non-negative")
    try:
        retrieved_at = datetime.fromisoformat(att["retrieved_at_utc"][:-1] + "+00:00")
    except ValueError as exc:
        raise AttestationError("BLOCK: malformed retrieval timestamp") from exc
    now = now_utc if now_utc is not None else datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")
    now = now.astimezone(timezone.utc)
    age = now - retrieved_at.astimezone(timezone.utc)
    if age > max_age:
        raise AttestationError("BLOCK: attestation is stale")
    if age < -allowed_future_skew:
        raise AttestationError("BLOCK: attestation timestamp is in the future")
    for field in ("retrieval_tool", "retrieval_tool_version", "signer_key_id"):
        if not isinstance(att[field], str) or not att[field].strip():
            raise AttestationError(f"BLOCK: {field} missing")
    if att["signer_key_id"] != configured_key_id:
        raise AttestationError("BLOCK: signer key identity does not match protected configuration")
    chain = att["redirect_chain"]
    if not isinstance(chain, list) or not chain:
        raise AttestationError("BLOCK: redirect chain must include final response")
    for index, hop in enumerate(chain):
        if (
            not isinstance(hop, dict)
            or not _validate_https_url(hop.get("url"))
            or type(hop.get("status")) is not int
            or not 100 <= hop["status"] <= 599
        ):
            raise AttestationError("BLOCK: malformed redirect-chain hop")
        if index < len(chain) - 1:
            if not 300 <= hop["status"] <= 399:
                raise AttestationError("BLOCK: non-final redirect hop must have a 3xx status")
            if hop.get("next_url") != chain[index + 1]["url"]:
                raise AttestationError("BLOCK: redirect chain does not bind each next URL")
        elif not 200 <= hop["status"] <= 299:
            raise AttestationError("BLOCK: final response must have a 2xx status")
    if chain[0]["url"] != att["requested_url"] or chain[-1]["url"] != att["final_url"]:
        raise AttestationError("BLOCK: redirect chain URL mismatch")
    if not isinstance(att["source_context"], dict):
        raise AttestationError("BLOCK: source context must be an object")
    missing_expected = REQUIRED_CONTEXT_FIELDS - set(expected_context)
    missing_attested = REQUIRED_CONTEXT_FIELDS - set(att["source_context"])
    if missing_expected or missing_attested:
        raise AttestationError(
            "BLOCK: source context is missing required scope fields "
            f"(expected={sorted(missing_expected)}, attested={sorted(missing_attested)})"
        )
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
        "requested_url": att["requested_url"],
        "final_url": att["final_url"],
    }
