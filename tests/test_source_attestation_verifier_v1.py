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
    raw = b"authoritative source bytes\x00\x01"
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
    with pytest.raises(AttestationError, match="trust root"):
        verify_attestation(
            snapshot_path=snapshot,
            attestation_path=att,
            expected_context={},
        )


def test_valid_signed_snapshot_verifies(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
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
    snapshot.write_bytes(snapshot.read_bytes() + b"!")
    with pytest.raises(AttestationError, match="SHA-256 mismatch"):
        verify_attestation(
            snapshot_path=snapshot,
            attestation_path=attestation,
            expected_context={"venue": "example"},
        )


def test_forged_final_url_without_resigning_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    att["final_url"] = "https://attacker.invalid/forged"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="redirect chain URL mismatch"):
        verify_attestation(
            snapshot_path=snapshot,
            attestation_path=attestation,
            expected_context={"venue": "example"},
        )


def test_context_mismatch_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, _ = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    with pytest.raises(AttestationError, match="source context mismatch"):
        verify_attestation(
            snapshot_path=snapshot,
            attestation_path=attestation,
            expected_context={"product": "ETH_USDT"},
        )


def test_unknown_schema_blocks_even_if_signed(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    att["schema_version"] = "future-unsupported"
    # Deliberately do not re-sign: schema rejection must happen before signature checks.
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="unsupported attestation schema"):
        verify_attestation(
            snapshot_path=snapshot,
            attestation_path=attestation,
            expected_context={},
        )



def test_redirect_chain_must_match_signed_requested_and_final_urls(tmp_path, monkeypatch):
    snapshot, attestation, public, att = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    att["redirect_chain"][0]["url"] = "https://attacker.invalid/unrecorded-hop"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="redirect chain URL mismatch"):
        verify_attestation(
            snapshot_path=snapshot,
            attestation_path=attestation,
            expected_context={"venue": "example"},
        )
