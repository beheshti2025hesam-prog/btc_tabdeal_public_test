import base64
import hashlib
from datetime import datetime, timedelta, timezone
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
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
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
    return snapshot, path, base64.b64encode(public).decode(), att, private


def _resign_attestation(path, att, private):
    att.pop("signature", None)
    att["signature"] = base64.b64encode(private.sign(_canonical_payload(att))).decode()
    path.write_text(json.dumps(att), encoding="utf-8")


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
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
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
    snapshot, attestation, public, _, _private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    snapshot.write_bytes(snapshot.read_bytes() + b"!")
    with pytest.raises(AttestationError, match="SHA-256 mismatch"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={"venue": "example"})


def test_forged_final_url_without_resigning_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["final_url"] = "https://attacker.invalid/forged"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="redirect chain URL mismatch"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={"venue": "example"})


def test_context_mismatch_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, _, _private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    with pytest.raises(AttestationError, match="source context mismatch"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={"product": "ETH_USDT"})


def test_unknown_schema_blocks_even_if_signed(tmp_path, monkeypatch):
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["schema_version"] = "future-unsupported"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="unsupported attestation schema"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_redirect_chain_must_match_signed_requested_and_final_urls(tmp_path, monkeypatch):
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["redirect_chain"][0]["url"] = "https://attacker.invalid/unrecorded-hop"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="redirect chain URL mismatch"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={"venue": "example"})



def test_stale_attestation_with_valid_signature_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    att["retrieved_at_utc"] = (now - timedelta(days=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
    _resign_attestation(attestation, att, private)
    with pytest.raises(AttestationError, match="attestation is stale"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={}, now_utc=now)


def test_future_dated_attestation_with_valid_signature_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    att["retrieved_at_utc"] = (now + timedelta(minutes=10)).isoformat(timespec="seconds").replace("+00:00", "Z")
    _resign_attestation(attestation, att, private)
    with pytest.raises(AttestationError, match="timestamp is in the future"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={}, now_utc=now)


@pytest.mark.parametrize("age", [timedelta(hours=24), timedelta(minutes=-5)])
def test_exact_freshness_boundaries_are_accepted(tmp_path, monkeypatch, age):
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    att["retrieved_at_utc"] = (now - age).isoformat(timespec="seconds").replace("+00:00", "Z")
    _resign_attestation(attestation, att, private)
    result = verify_attestation(
        snapshot_path=snapshot,
        attestation_path=attestation,
        expected_context={},
        now_utc=now,
    )
    assert result["verified"] is True


def test_naive_verification_clock_is_rejected(tmp_path, monkeypatch):
    snapshot, attestation, public, _, _private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    with pytest.raises(ValueError, match="now_utc must be timezone-aware"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={}, now_utc=datetime(2026, 10, 12))


def test_timestamp_must_be_explicit_utc(tmp_path, monkeypatch):
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["retrieved_at_utc"] = "2026-10-11T00:00:00+03:00"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="timestamp"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_redirect_hops_must_bind_next_url_and_status(tmp_path, monkeypatch):
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
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
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["requested_url"] = "https://user:pass@api.example.invalid/docs"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="HTTPS URLs"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_signer_key_id_must_match_protected_identity(tmp_path, monkeypatch):
    snapshot, attestation, public, _, _private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "different-protected-key")
    with pytest.raises(AttestationError, match="identity does not match"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_signature_tampering_blocks(tmp_path, monkeypatch):
    snapshot, attestation, public, att, private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    att["retrieval_tool_version"] = "tampered-after-signing"
    attestation.write_text(json.dumps(att), encoding="utf-8")
    with pytest.raises(AttestationError, match="invalid key, signature, or attestation encoding"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_wrong_public_key_blocks(tmp_path, monkeypatch):
    snapshot, attestation, _, _, _private = _signed_fixture(tmp_path)
    other_private = Ed25519PrivateKey.generate()
    other_public = other_private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", base64.b64encode(other_public).decode())
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "test-key")
    with pytest.raises(AttestationError, match="invalid key, signature, or attestation encoding"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})


def test_missing_key_identity_blocks_even_with_public_key(tmp_path, monkeypatch):
    snapshot, attestation, public, _, _private = _signed_fixture(tmp_path)
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", public)
    monkeypatch.delenv("HES_SOURCE_ATTESTATION_KEY_ID", raising=False)
    with pytest.raises(AttestationError, match="trust root"):
        verify_attestation(snapshot_path=snapshot, attestation_path=attestation, expected_context={})
