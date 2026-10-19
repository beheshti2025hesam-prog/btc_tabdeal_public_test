"""Tamper-evident diagnostic details for evidence producers.

Diagnostic details are deliberately separate from the canonical gate-state
digest. They can be verified independently without changing promotion policy.
"""
from __future__ import annotations

import hashlib
import json


def diagnostics_digest(details: tuple[tuple[str, str], ...] | list[tuple[str, str]]) -> str:
    normalized = tuple(sorted((str(k), str(v)) for k, v in details))
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def verify_diagnostics(
    details: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    digest: str,
) -> bool:
    return diagnostics_digest(details) == digest
