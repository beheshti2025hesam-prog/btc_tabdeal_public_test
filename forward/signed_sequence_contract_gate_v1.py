"""Strict adapter for the signed sequence-contract evidence verifier.

This adapter deliberately does not infer trust from booleans or evidence-reference
strings. Callers must supply the exact envelope, trusted key registry, expected
commit, evidence path, and market scope.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.verify_signed_source_evidence_v1 import verify


def verify_sequence_contract_evidence(
    *,
    envelope_path: str | Path,
    key_registry_path: str | Path,
    expected_commit: str,
    expected_evidence_path: str,
    market_scope: str,
    max_age_seconds: int = 86400,
    now=None,
) -> dict[str, Any]:
    """Return verifier metadata or raise; callers must fail closed on any error."""
    envelope_bytes = Path(envelope_path).read_bytes()
    key_registry_bytes = Path(key_registry_path).read_bytes()
    envelope = json.loads(envelope_bytes.decode("utf-8"))
    key_registry = json.loads(key_registry_bytes.decode("utf-8"))
    if not isinstance(key_registry, dict) or not key_registry:
        raise ValueError("trusted key registry must be a non-empty object")
    result = verify(
        envelope,
        expected_commit=expected_commit,
        expected_path=expected_evidence_path,
        market_scope=market_scope,
        key_registry=key_registry,
        max_age_seconds=max_age_seconds,
        now=now,
    )
    if result.get("status") != "VERIFIED":
        raise ValueError("sequence contract evidence was not verified")
    # Pin the exact envelope and trust-registry bytes used for this decision.
    # A later audit must not silently substitute a re-serialized envelope or rotated key file.
    return {
        **result,
        "envelope_sha256": hashlib.sha256(envelope_bytes).hexdigest(),
        "key_registry_sha256": hashlib.sha256(key_registry_bytes).hexdigest(),
    }
