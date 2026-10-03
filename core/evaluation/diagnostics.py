"""Tamper-evident diagnostics binding for promotion audit records."""

from __future__ import annotations

import hashlib
import json


def diagnostics_digest(
    details: tuple[tuple[str, str], ...] | list[tuple[str, str]],
) -> str:
    normalized = tuple(sorted((str(key), str(value)) for key, value in details))
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def verify_diagnostics(
    details: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    digest: str,
) -> bool:
    return diagnostics_digest(details) == digest
