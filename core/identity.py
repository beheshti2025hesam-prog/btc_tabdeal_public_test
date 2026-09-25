"""Canonical application identity for HES Trade Agent.

This module is intentionally the single source of truth for application identity.
The values are compile-time constants, not user configuration.
"""

from __future__ import annotations

import hashlib

APP_NAME = "HES Trade Agent"
OWNER_NAME = "Seyed Hesameddin Beheshti Shirazi"

_EXPECTED_IDENTITY_FINGERPRINT = (
    "24b913266e6a49e8df14884c3c0288cdbb3276b9bbc54ca7115a0d1abf2582b3"
)


def validate_identity() -> None:
    """Fail closed if the canonical identity has been altered."""
    actual = hashlib.sha256(
        f"{APP_NAME}\n{OWNER_NAME}".encode("utf-8")
    ).hexdigest()
    if actual != _EXPECTED_IDENTITY_FINGERPRINT:
        raise RuntimeError("HES Trade Agent identity integrity check failed.")


__all__ = ["APP_NAME", "OWNER_NAME", "validate_identity"]
