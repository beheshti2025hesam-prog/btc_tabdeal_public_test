"""Strict cryptographic and semantic gate for signed sequence-contract evidence.

The envelope carries raw source snapshot bytes plus a separately typed contract
claim. A valid signature proves who signed the bytes; it does not make arbitrary
bytes or unsupported claims a valid sequence contract.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.verify_signed_source_evidence_v1 import verify


class SequenceContractPayloadError(ValueError):
    """Signed envelope is not a complete, scoped sequence-contract assertion."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SequenceContractPayloadError("duplicate JSON key in signed evidence")
        result[key] = value
    return result


def _validate_contract(envelope: dict[str, Any], raw_source_bytes: bytes, market_scope: str) -> dict[str, Any]:
    expected_envelope_keys = {
        "expected_commit", "evidence_path", "raw_sha256", "source_url",
        "redirect_chain", "retrieved_at", "market_scope", "key_id",
        "signature_algorithm", "payload_b64", "signature_b64", "sequence_contract",
    }
    if set(envelope) != expected_envelope_keys:
        raise SequenceContractPayloadError("signed envelope has missing or unexpected fields")

    contract = envelope.get("sequence_contract")
    required = {
        "schema", "status", "market_scope", "venue", "product", "symbol",
        "endpoint", "channel_or_topic", "message_type", "field_path",
        "protocol_version", "semantic_class", "capabilities", "source_evidence",
    }
    if not isinstance(contract, dict) or set(contract) != required:
        raise SequenceContractPayloadError("signed contract has missing or unexpected fields")

    expected = {
        "schema": "hes_sequence_contract_attestation_v1",
        "status": "verified",
        "market_scope": market_scope,
        "venue": "tabdeal",
        "product": "fapi-futures-margin",
        "symbol": "BTC_USDT",
        "endpoint": "wss://api1.tabdeal.org/special_margin/broadcast/",
        "channel_or_topic": "BTC_USDT raw-text subscription",
        "message_type": "trade-envelope",
        "field_path": "trade.sequence",
        "protocol_version": "unknown",
        "semantic_class": "message_sequence",
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise SequenceContractPayloadError("signed contract scope or status mismatch")

    capabilities = contract.get("capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != {
        "unique", "ordered", "contiguous", "comparable_across_reconnect"
    }:
        raise SequenceContractPayloadError("sequence capabilities are incomplete or unexpected")
    if any(type(capabilities[key]) is not bool for key in capabilities):
        raise SequenceContractPayloadError("sequence capabilities must be strict booleans")
    # Minimum claims needed before this stream's sequence may be used for
    # ordering and gap-sensitive observation. Unknown/false never pass.
    if capabilities != {
        "unique": True,
        "ordered": True,
        "contiguous": True,
        "comparable_across_reconnect": False,
    }:
        raise SequenceContractPayloadError("required sequence capabilities are not proven")

    evidence = contract.get("source_evidence")
    evidence_keys = {
        "source_kind", "source_url", "retrieved_at",
        "source_snapshot_sha256", "evidence_excerpt",
    }
    if not isinstance(evidence, dict) or set(evidence) != evidence_keys:
        raise SequenceContractPayloadError("source evidence is incomplete or has unexpected fields")
    if evidence.get("source_kind") != "primary":
        raise SequenceContractPayloadError("sequence contract requires primary-source evidence")

    source_url = evidence.get("source_url")
    try:
        parsed = urlparse(source_url) if isinstance(source_url, str) else None
        valid_url = (
            parsed is not None and parsed.scheme == "https"
            and parsed.hostname == "docs.tabdeal.org"
            and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        valid_url = False
    if not valid_url or source_url != envelope.get("source_url"):
        raise SequenceContractPayloadError("source evidence URL is not the signed Tabdeal documentation source")

    stamp = evidence.get("retrieved_at")
    if not isinstance(stamp, str) or not stamp.strip() or stamp != envelope.get("retrieved_at"):
        raise SequenceContractPayloadError("source evidence retrieval time does not match signed envelope")

    digest = evidence.get("source_snapshot_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SequenceContractPayloadError("source snapshot SHA-256 is invalid or missing")
    if not hmac.compare_digest(digest, envelope.get("raw_sha256", "")):
        raise SequenceContractPayloadError("source snapshot digest does not match signed raw payload")

    excerpt = evidence.get("evidence_excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip():
        raise SequenceContractPayloadError("source evidence excerpt is missing")
    try:
        source_text = raw_source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SequenceContractPayloadError("source snapshot is not UTF-8") from exc
    if excerpt not in source_text:
        raise SequenceContractPayloadError("source evidence excerpt is not present in signed source snapshot")
    return contract


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
    """Return verified metadata or raise; callers must fail closed on any error."""
    envelope_bytes = Path(envelope_path).read_bytes()
    key_registry_bytes = Path(key_registry_path).read_bytes()

    # This digest must come from deployment-owned protected configuration,
    # not from the same repository/workspace as the registry and envelope.
    trusted_registry_sha256 = os.environ.get("HES_TRUSTED_KEY_REGISTRY_SHA256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", trusted_registry_sha256):
        raise ValueError("independent trusted key-registry SHA-256 is not configured")
    actual_registry_sha256 = hashlib.sha256(key_registry_bytes).hexdigest()
    if not hmac.compare_digest(actual_registry_sha256, trusted_registry_sha256):
        raise ValueError("trusted key-registry SHA-256 mismatch")

    envelope = json.loads(envelope_bytes.decode("utf-8"), object_pairs_hook=_unique_object)
    key_registry = json.loads(key_registry_bytes.decode("utf-8"), object_pairs_hook=_unique_object)
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
        raw_source_bytes = base64.b64decode(envelope["payload_b64"], validate=True)
    except Exception as exc:
        raise SequenceContractPayloadError("signed source snapshot is not valid base64") from exc
    contract = _validate_contract(envelope, raw_source_bytes, market_scope)
    return {
        **result,
        "sequence_contract_schema": contract["schema"],
        "sequence_contract_semantic_class": contract["semantic_class"],
        "sequence_contract_capabilities": contract["capabilities"],
        "sequence_contract_capabilities_json": json.dumps(
            contract["capabilities"], sort_keys=True, separators=(",", ":")
        ),
        "source_snapshot_sha256": contract["source_evidence"]["source_snapshot_sha256"],
        "envelope_sha256": hashlib.sha256(envelope_bytes).hexdigest(),
        "key_registry_sha256": hashlib.sha256(key_registry_bytes).hexdigest(),
    }
