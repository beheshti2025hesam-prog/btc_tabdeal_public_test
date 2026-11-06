"""Exact-scope fail-closed gate for Tabdeal trade.sequence semantics."""
from __future__ import annotations
from typing import Any
from .sequence_semantics_registry_v1 import load_default_registry

TABDEAL_BROADCAST_TRADE_SEQUENCE_SCOPE = {
    "venue": "tabdeal",
    "product": "fapi_futures_margin",
    "endpoint": "wss://api1.tabdeal.org/special_margin/broadcast/",
    "channel": "BTC_USDT_raw_text_subscription",
    "message_type": "trade_envelope",
    "field_path": "trade.sequence",
    "protocol_version": "unknown",
}
REQUIRED_TRADE_SEQUENCE_CAPABILITIES = (
    "event_identity_unique",
    "ordered_within_scope",
    "contiguous_within_scope",
    "gap_detectable",
)


def evaluate_tabdeal_trade_sequence_capabilities() -> dict[str, Any]:
    """Unknown or unsupported capabilities never grant sequence-based processing."""
    try:
        registry = load_default_registry()
        contract = registry.resolve(**TABDEAL_BROADCAST_TRADE_SEQUENCE_SCOPE)
    except Exception as exc:
        return {
            "safe": False,
            "reason": "SEQUENCE_REGISTRY_UNAVAILABLE",
            "scope": dict(TABDEAL_BROADCAST_TRADE_SEQUENCE_SCOPE),
            "capabilities": {},
            "missing_capabilities": list(REQUIRED_TRADE_SEQUENCE_CAPABILITIES),
            "error_type": type(exc).__name__,
        }
    if contract is None:
        return {
            "safe": False,
            "reason": "SEQUENCE_CONTRACT_NOT_FOUND",
            "scope": dict(TABDEAL_BROADCAST_TRADE_SEQUENCE_SCOPE),
            "capabilities": {},
            "missing_capabilities": list(REQUIRED_TRADE_SEQUENCE_CAPABILITIES),
        }
    capabilities = {
        name: registry.capability(contract, name)
        for name in REQUIRED_TRADE_SEQUENCE_CAPABILITIES
    }
    missing = [
        name for name in REQUIRED_TRADE_SEQUENCE_CAPABILITIES
        if not registry.may_claim(contract, name)
    ]
    return {
        "safe": not missing,
        "reason": "SEQUENCE_CAPABILITIES_VERIFIED" if not missing else "SEQUENCE_CAPABILITIES_UNVERIFIED",
        "scope": dict(TABDEAL_BROADCAST_TRADE_SEQUENCE_SCOPE),
        "registry_revision": registry.revision,
        "capabilities": capabilities,
        "missing_capabilities": missing,
        "evidence_refs": [
            row["evidence_ref"] for row in contract.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("evidence_ref"), str)
        ],
    }
