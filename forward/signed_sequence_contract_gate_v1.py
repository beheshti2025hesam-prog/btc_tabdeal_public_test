"""Strict adapter for the signed sequence-contract evidence verifier.

This adapter deliberately does not infer trust from booleans or evidence-reference
strings. Callers must supply the exact envelope, trusted key registry, expected
commit, evidence path, and market scope.
"""
from __future__ import annotations

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
    envelope = json.loads(Path(envelope_path).read_text(encoding="utf-8"))
    key_registry = json.loads(Path(key_registry_path).read_text(encoding="utf-8"))
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
    return result
