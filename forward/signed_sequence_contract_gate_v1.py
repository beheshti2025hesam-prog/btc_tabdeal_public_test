"""Strict verifier and structural validator for signed sequence contracts."""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from scripts.verify_signed_source_evidence_v1 import verify

_CAPABILITY_KEYS = (
    "exact_replay_dedup",
    "event_id_dedup",
    "ordered_within_scope",
    "contiguous_within_scope",
    "gap_detectable",
    "cross_reconnect",
)
_SEMANTIC_CLASSES = {
    "unknown", "opaque_id", "event_id", "message_sequence",
    "book_update_range", "timestamp", "cursor",
}


def validate_sequence_contract_payload(payload: bytes, *, market_scope: str) -> dict[str, Any]:
    """Validate the signed payload's structure and capability implications.

    A valid signature authenticates bytes; this function establishes whether
    those bytes describe the exact adapter scope and which operations are
    authorized. Unknown capabilities remain false/unknown, never inferred.
    """
    try:
        contract = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("sequence contract payload must be UTF-8 JSON") from exc
    if not isinstance(contract, dict):
        raise ValueError("sequence contract must be an object")

    required_strings = {
        "schema": "hes_sequence_contract_v1",
        "venue": "tabdeal",
        "product": "futures_margin",
        "endpoint": "special_margin/broadcast/",
        "channel": "trade_broadcast",
        "message_type": "trade",
        "field_path": "trade.sequence",
        "scope": market_scope,
    }
    for key, expected in required_strings.items():
        value = contract.get(key)
        if not isinstance(value, str) or value != expected:
            raise ValueError(f"sequence contract {key} mismatch")

    semantic_class = contract.get("semantic_class")
    # Check the type before set membership: JSON arrays/objects are unhashable
    # and must fail closed with the documented validation error, not TypeError.
    if not isinstance(semantic_class, str) or semantic_class not in _SEMANTIC_CLASSES:
        raise ValueError("invalid sequence contract semantic_class")
    protocol_version = contract.get("protocol_version")
    if not isinstance(protocol_version, str) or not protocol_version.strip():
        raise ValueError("sequence contract protocol_version is required")

    capabilities = contract.get("capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != set(_CAPABILITY_KEYS):
        raise ValueError("sequence contract capabilities are incomplete or unexpected")
    if any(type(capabilities[key]) is not bool for key in _CAPABILITY_KEYS):
        raise ValueError("sequence contract capabilities must be booleans")
    if capabilities["event_id_dedup"] and semantic_class != "event_id":
        raise ValueError("event_id_dedup requires semantic_class=event_id")
    if capabilities["contiguous_within_scope"] and not capabilities["ordered_within_scope"]:
        raise ValueError("contiguous capability requires ordered capability")
    if capabilities["gap_detectable"] and not capabilities["contiguous_within_scope"]:
        raise ValueError("gap detection requires contiguous capability")
    if capabilities["cross_reconnect"] and not capabilities["ordered_within_scope"]:
        raise ValueError("cross-reconnect capability requires ordered capability")
    if semantic_class == "unknown" and any(
        capabilities[key]
        for key in (
            "event_id_dedup",
            "ordered_within_scope",
            "contiguous_within_scope",
            "gap_detectable",
            "cross_reconnect",
        )
    ):
        raise ValueError("unknown semantic_class cannot authorize identity or ordering capabilities")

    return {
        "schema": contract["schema"],
        "venue": contract["venue"],
        "product": contract["product"],
        "endpoint": contract["endpoint"],
        "channel": contract["channel"],
        "message_type": contract["message_type"],
        "field_path": contract["field_path"],
        "scope": contract["scope"],
        "protocol_version": protocol_version,
        "semantic_class": semantic_class,
        "capabilities": dict(capabilities),
    }


def verify_sequence_contract_evidence(
    *,
    envelope_path: str | Path,
    key_registry_path: str | Path,
    expected_commit: str,
    expected_evidence_path: str,
    market_scope: str,
    trusted_key_registry_sha256: str,
    max_age_seconds: int = 86400,
    now=None,
) -> dict[str, Any]:
    """Return cryptographic and structural verification metadata or raise."""
    envelope_bytes = Path(envelope_path).read_bytes()
    key_registry_bytes = Path(key_registry_path).read_bytes()
    if not isinstance(trusted_key_registry_sha256, str) or len(trusted_key_registry_sha256) != 64:
        raise ValueError("independent trusted registry SHA-256 pin is required")
    if any(ch not in "0123456789abcdef" for ch in trusted_key_registry_sha256):
        raise ValueError("invalid independent trusted registry SHA-256 pin")
    actual_registry_sha256 = hashlib.sha256(key_registry_bytes).hexdigest()
    if not hmac.compare_digest(actual_registry_sha256, trusted_key_registry_sha256):
        raise ValueError("trusted key registry identity mismatch")

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

    try:
        payload = __import__("base64").b64decode(envelope["payload_b64"], validate=True)
    except Exception as exc:
        raise ValueError("invalid signed contract payload encoding") from exc
    contract = validate_sequence_contract_payload(payload, market_scope=market_scope)
    return {
        **result,
        "contract": contract,
        "envelope_sha256": hashlib.sha256(envelope_bytes).hexdigest(),
        "key_registry_sha256": actual_registry_sha256,
        "contract_payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
