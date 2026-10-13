"""Adversarial tests for non-empty source scope and reviewed commit identity."""
import base64
import hashlib
import json
from datetime import datetime, timezone

import pytest

from forward.source_attestation_verifier_v1 import (
    AttestationError, _canonical_payload, verify_attestation,
)

cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


CONTEXT = {
    "venue": "example",
    "product": "BTC_USDT",
    "endpoint": "/special_margin/broadcast/",
    "channel": "trade",
    "message_type": "trade",
    "field": "trade.sequence",
    "protocol_version": "unknown",
    "reviewed_commit_sha": "a" * 40,
    "contract_version": "sequence-semantics/1",
}


def make_fixture(tmp_path, monkeypatch, *, context=None):
    raw = b"synthetic source bytes"
    snapshot = tmp_path / "source.bin"
    snapshot.write_bytes(raw)
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    att = {
        "schema_version": "hes-source-attestation-v1",
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "requested_url": "https://api.example.invalid/docs",
        "final_url": "https://api.example.invalid/docs",
        "redirect_chain": [{"url": "https://api.example.invalid/docs", "status": 200}],
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "retrieval_tool": "synthetic-test",
        "retrieval_tool_version": "1",
        "source_context": dict(CONTEXT if context is None else context),
        "signer_key_id": "test-key",
    }
    att["signature"] = base64.b64encode(private.sign(_canonical_payload(att))).decode("ascii")
    att_path = tmp_path / "attestation.json"
    att_path.write_text(json.dumps(att), encoding="utf-8")
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", base64.b64encode(public).decode("ascii"))
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    return snapshot, att_path, att, private


@pytest.mark.parametrize("field,value", [
    ("venue", ""),
    ("product", "   "),
    ("endpoint", None),
    ("contract_version", 1),
])
def test_empty_or_non_string_required_attested_context_blocks(tmp_path, monkeypatch, field, value):
    context = dict(CONTEXT)
    context[field] = value
    snapshot, att_path, att, private = make_fixture(tmp_path, monkeypatch, context=context)
    # Sign the intentionally malformed context correctly: rejection must be due to scope validation.
    att["signature"] = base64.b64encode(private.sign(_canonical_payload(att))).decode("ascii")
    att_path.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="must be a non-empty string"):
        verify_attestation(snapshot_path=snapshot, attestation_path=att_path, expected_context=CONTEXT)


@pytest.mark.parametrize("sha", ["unknown", "A" * 40, "a" * 39, ""])
def test_malformed_reviewed_commit_sha_blocks(tmp_path, monkeypatch, sha):
    context = dict(CONTEXT)
    context["reviewed_commit_sha"] = sha
    snapshot, att_path, att, private = make_fixture(tmp_path, monkeypatch, context=context)
    att["signature"] = base64.b64encode(private.sign(_canonical_payload(att))).decode("ascii")
    att_path.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="reviewed_commit_sha"):
        verify_attestation(snapshot_path=snapshot, attestation_path=att_path, expected_context=context)


def test_empty_expected_context_value_blocks_even_when_attestation_has_value(tmp_path, monkeypatch):
    snapshot, att_path, _att, _private = make_fixture(tmp_path, monkeypatch)
    expected = dict(CONTEXT)
    expected["channel"] = " "
    with pytest.raises(AttestationError, match="must be a non-empty string"):
        verify_attestation(snapshot_path=snapshot, attestation_path=att_path, expected_context=expected)
