"""Synthetic-only registry fixture. Never use this evidence in production."""
import hashlib
import json

from forward.sequence_semantics_v1 import (
    DEFAULT_TABDEAL_TRADE_RECORD_ID,
    TABDEAL_TRADE_SEQUENCE_KEY,
    SequenceSemanticsRegistryV1,
)


def verified_tabdeal_test_registry():
    payload = {
        "schema": "hes_sequence_semantics_registry_v1",
        "registry_version": 1,
        "records": [{
            "record_id": DEFAULT_TABDEAL_TRADE_RECORD_ID,
            "key": TABDEAL_TRADE_SEQUENCE_KEY,
            "semantic_class": "ORDERED_EVENT_SEQUENCE",
            "scope": ["symbol"],
            "claims": {"ordered": True, "contiguous": False},
            "capabilities": {
                "event_identity": True,
                "contiguous_gap_detection": False,
                "snapshot_bootstrap": False,
                "exact_payload_replay_only": True,
            },
            "source_evidence": {
                "source_kind": "primary",
                "source_content_sha256": "a" * 64,
            },
            "status": "VERIFIED",
        }],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return SequenceSemanticsRegistryV1(
        payload, raw_sha256=hashlib.sha256(raw).hexdigest()
    )
