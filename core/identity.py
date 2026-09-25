"""Canonical application identity for HRS Trade Agent.

This module is intentionally the single source of truth for application identity.
The values are compile-time constants, not user configuration.
"""

from __future__ import annotations

import hashlib

APP_NAME = "HRS Trade Agent"
OWNER_NAME = "Seyed Hesameddin Beheshti Shirazi"

# Fixed integrity fingerprint of the canonical identity values.
_IDENTITY_FINGERPRINT = hashlib.sha256(
    f"{APP_NAME}\n{OWNER_NAME}".encode("utf-8")
).hexdigest()

# The expected fingerprint is embedded separately so accidental edits to either
# canonical value fail closed at runtime.
_EXPECTED_IDENTITY_FINGERPRINT = (
    "d8cf1ec0cc866f0924d0c662d15ac83b597bbb638d9b38458beaa60590dd6dc0"
)


def validate_identity() -> None:
    """Fail closed if the canonical identity has been altered."""
    actual = hashlib.sha256(
        f"{APP_NAME}\n{OWNER_NAME}".encode("utf-8")
    ).hexdigest()
    if actual != _EXPECTED_IDENTITY_FINGERPRINT:
        raise RuntimeError("HRS Trade Agent identity integrity check failed.")


__all__ = ["APP_NAME", "OWNER_NAME", "validate_identity"]
