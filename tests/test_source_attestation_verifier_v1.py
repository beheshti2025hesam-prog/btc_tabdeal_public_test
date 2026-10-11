import base64
import hashlib
import json

import pytest

from forward.source_attestation_verifier_v1 import (
    AttestationError,
    _canonical_payload,
    verify_attestation,
)

cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _signed_fixture(tmp_path):
    snapshot = tmp_path / "source.bin"
    raw = b"authoritative source bytes\\x00\\x01"
    snapshot.write_bytes(raw)
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    att = {
        "schema_version": "hes-source-attestation-v1",
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "requested_url": "https://api.example.invalid/docs",
        "final_url": "https://api.example.invalid/docs",
        "redirect_chain": [
            {"url": "https://api.example.invalid/docs", "status": 200}
        ],
        "retrieved_at_utc": "2026-10-11T00:00:00Z",
        "retrieval_tool": "controlled-attestor",
        "retrieval_tool_version": "1.0",
        "source_context": {
            "venue": "example",
            "product": "BTC_USDT",
            "channel": "trades",
            "field": "trade.sequence",
        },
        "signer_key_id": "test-key",
    }
    att["signature"] = base64.b64encode(private.sign(_canonical_payload(att))).decode()
    path = tmp_path / "attestation.json"
    path.write_text(json.dumps(att), encoding="utf-8")
    return snapshot, path, base64.b64encode(public).decode(), att


def test_missing_external_trust_root_blocks(tmp_path, monkeypatch):
    snapshot = tmp_path / "source.bin"
    snapshot.write_bytes(b"x")
    att = tmp_path / "attestation.json"
    att.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", raising=False)
    monkeypatch.delenv("HES_SOURCE_ATTESTATION_KEY_ID", raising=False)
    with pytest.raises(AttestationError, match="trust root"):
        verify_attestation(snapshot_path=snapshot, attestation_path=att, expected_context={})


def test_valid_signed_snapshot_verifies(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    result = verify_attestation(
        snapshot_path=snapshot,
        attestation_path=attestation,
        expected_context={"venue": "example", "product": "BTC_USDT"},
    )
    assert result["verified"] is True
    assert result["snapshot_sha256"] == att["snapshot_sha256"]


def test_one_byte_snapshot_change_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, _ = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    snapshot.write_bytes(snapshot.read_bytes() + b"!")
    with pytest.raises(AttestationError, match="SHA-256 mismatch"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={"venue": "example"})


def test_forged_final_url_without_resigning_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["final_url"] = "https://attacker.invalid/forged"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="redirect chain URL mismatch"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={"venue": "example"})


def test_context_mismatch_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, _ = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    with pytest.raises(AttestationError, match="source context mismatch"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={"product": "ETH_USDT"})


def test_unknown_schema_blocks_even_if_signed(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["schema_version"] = "future-unsupported"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="unsupported attestation schema"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_redirect_chain_must_match_signed_requested_and_final_urls(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["redirect_chain"][0]["url"] = "https://attacker.invalid/unrecorded-hop"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="redirect chain URL mismatch"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={"venue": "example"})


def test_timestamp_must_be_explicit_utc(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["retrieved_at_utc"] = "2026-10-11T00:00:00+03:00"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="timestamp"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_redirect_hops_must_bind_next_url_and_status(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    first = "https://api.example.invalid/docs"
    final = "https://docs.example.invalid/current"
    att["final_url"] = final
    att["redirect_chain"] = [
        {"url": first, "status": 302, "next_url": "https://attacker.invalid/"},
        {"url": final, "status": 200},
    ]
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="does not bind each next URL"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_non_https_or_credentialed_url_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["requested_url"] = "https://user:pass@api.example.invalid/docs"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="HTTPS URLs"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_signer_key_id_must_match_protected_identity(tmp_path, monkeypatch):
    snapshot, attestation, public, _ = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "different-protected-key")
    with pytest.raises(AttestationError, match="identity does not match"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_signature_tampering_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["retrieval_tool_version"] = "tampered-after-signing"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="invalid key, signature, or attestation encoding"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_wrong_public_key_blocks(tmp_path, monkeypatch):
    snapshot, attestation, _, _ = _signed_fixture(tmp_path)
    other_private = Ed25519PrivateKey.generate()
    other_public = other_private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", base64.b64encode(other_public).decode())
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    with pytest.raises(AttestationError, match="invalid key, signature, or attestation encoding"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_missing_key_identity_blocks_even_with_public_key(tmp_path, monkeypatch):
    snapshot, attestation, public, _ = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.delenv("HES_SOURCE_ATTESTATION_KEY_ID", raising=False)
    with pytest.raises(AttestationError, match="trust root"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})
