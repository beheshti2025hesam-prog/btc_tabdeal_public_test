"""Fail-closed verifier for externally signed source-provenance attestations.

Trust material is supplied out-of-band via environment variables:
HES_TRUSTED_ED25519_PUBLIC_KEY_B64 and HES_TRUSTED_KEY_ID.
The private key must never be stored in this repository.
The detached signature covers the exact decoded payload bytes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import re
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class AttestationError(ValueError):
    pass


_ALLOWED_SOURCE_HOSTS = frozenset({
    "docs.tabdeal.org", "tabdeal.org", "www.tabdeal.org", "api1.tabdeal.org",
})
_MAX_ATTESTATION_AGE = timedelta(hours=24)
_ALLOWED_FUTURE_SKEW = timedelta(minutes=5)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AttestationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(raw: str | bytes, label: str) -> object:
    try:
        return json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              AttestationError(f"non-finite JSON value in {label}")))
    except AttestationError:
        raise
    except Exception as exc:
        raise AttestationError(f"{label} is unreadable or invalid JSON") from exc


def _validate_source_url(value: object, label: str) -> None:
    try:
        parsed = urlparse(value) if isinstance(value, str) else None
        valid = bool(
            parsed and parsed.scheme == "https" and parsed.hostname
            and parsed.hostname.lower() in _ALLOWED_SOURCE_HOSTS
            and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        # urlparse(...).port can raise for malformed ports or bracketed hosts.
        valid = False
    if not valid:
        raise AttestationError(f"{label} is not an allowed official Tabdeal HTTPS URL")


def _b64(value: object, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise AttestationError(f"missing or invalid {label}")
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise AttestationError(f"invalid base64 for {label}") from exc


def verify_attestation(
    attestation_path: str | Path,
    artifact_path: str | Path,
    *,
    expected_commit: str,
    trusted_key_id: str | None,
    trusted_public_key_b64: str | None,
    now_utc: datetime | None = None,
    max_age: timedelta = _MAX_ATTESTATION_AGE,
    allowed_future_skew: timedelta = _ALLOWED_FUTURE_SKEW,
) -> dict:
    """Verify detached Ed25519 signature, artifact digest, source URL and commit."""
    if not trusted_key_id or not trusted_public_key_b64:
        raise AttestationError("external trust configuration is missing")
    envelope = _strict_json(Path(attestation_path).read_text(encoding="utf-8"), "attestation envelope")
    if not isinstance(envelope, dict):
        raise AttestationError("attestation envelope must be a JSON object")
    if set(envelope) != {"schema_version", "key_id", "payload_b64", "signature_b64"}:
        raise AttestationError("attestation envelope has missing or unexpected fields")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1:
        raise AttestationError("unsupported attestation envelope schema")
    if envelope["key_id"] != trusted_key_id:
        raise AttestationError("attestation key_id does not match externally trusted key")

    payload_bytes = _b64(envelope.get("payload_b64"), "payload_b64")
    signature = _b64(envelope["signature_b64"], "signature_b64")
    if len(signature) != 64:
        raise AttestationError("Ed25519 signature must be 64 bytes")
    public_key_bytes = _b64(trusted_public_key_b64, "trusted public key")
    if len(public_key_bytes) != 32:
        raise AttestationError("Ed25519 public key must be 32 bytes")
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, payload_bytes)
    except (InvalidSignature, ValueError) as exc:
        raise AttestationError("detached signature verification failed") from exc

    payload = _strict_json(payload_bytes.decode("utf-8"), "signed payload")
    required = {"schema_version", "source_url", "resolved_url", "raw_sha256",
                "commit_sha", "fetched_at", "tool_version", "contract_version"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise AttestationError("signed provenance payload has missing or unexpected fields")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise AttestationError("unsupported provenance payload schema")
    if not isinstance(expected_commit, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected_commit):
        raise AttestationError("expected commit must be a full 40- or 64-character lowercase hex SHA")
    if payload["commit_sha"] != expected_commit:
        raise AttestationError("attestation is for a different commit")
    if not isinstance(payload["raw_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", payload["raw_sha256"]):
        raise AttestationError("raw_sha256 must be a 64-character lowercase SHA-256 hex digest")
    for field in ("tool_version", "contract_version"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise AttestationError(f"{field} must be a non-empty string")
    if max_age < timedelta(0) or allowed_future_skew < timedelta(0):
        raise ValueError("max_age and allowed_future_skew must be non-negative")
    fetched_at = payload["fetched_at"]
    if not isinstance(fetched_at, str) or not fetched_at.strip():
        raise AttestationError("fetched_at must be an RFC 3339 timestamp with timezone")
    try:
        normalized_timestamp = fetched_at[:-1] + "+00:00" if fetched_at.endswith("Z") else fetched_at
        parsed_timestamp = datetime.fromisoformat(normalized_timestamp)
        if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
            raise ValueError("timezone is required")
    except (TypeError, ValueError) as exc:
        raise AttestationError("fetched_at must be a valid RFC 3339 timestamp with timezone") from exc
    now = now_utc if now_utc is not None else datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")
    age = now.astimezone(timezone.utc) - parsed_timestamp.astimezone(timezone.utc)
    if age > max_age:
        raise AttestationError("attestation is stale")
    if age < -allowed_future_skew:
        raise AttestationError("fetched_at is unacceptably far in the future")
    for field in ("source_url", "resolved_url"):
        _validate_source_url(payload[field], field)
    digest = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
    if payload["raw_sha256"] != digest:
        raise AttestationError("source artifact SHA-256 does not match signed provenance")
    return {"status": "VERIFIED", "key_id": trusted_key_id,
            "commit_sha": expected_commit, "artifact_sha256": digest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attestation", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_attestation(
            args.attestation, args.artifact,
            expected_commit=args.expected_commit,
            trusted_key_id=os.environ.get("HES_TRUSTED_KEY_ID"),
            trusted_public_key_b64=os.environ.get("HES_TRUSTED_ED25519_PUBLIC_KEY_B64"),
        )
    except (AttestationError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
