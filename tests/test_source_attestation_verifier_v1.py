import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from forward.source_attestation_verifier_v1 import AttestationError, verify_attestation


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


@pytest.fixture
def signed_case(tmp_path):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    artifact = tmp_path / "source.json"
    artifact.write_bytes(b'{"source":"official-doc-snapshot"}')
    payload = {
        "schema_version": 1,
        "source_url": "https://docs.tabdeal.org/",
        "resolved_url": "https://docs.tabdeal.org/api",
        "raw_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "commit_sha": "a" * 40,
        "fetched_at": "2026-10-12T00:00:00Z",
        "tool_version": "test-extractor/1",
        "contract_version": "sequence-semantics/1",
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    envelope = {
        "schema_version": 1,
        "key_id": "test-key-1",
        "payload_b64": b64(payload_bytes),
        "signature_b64": b64(private.sign(payload_bytes)),
    }
    attestation = tmp_path / "attestation.json"
    attestation.write_text(json.dumps(envelope), encoding="utf-8")
    return attestation, artifact, public, payload, envelope


def verify(case, **overrides):
    attestation, artifact, public, payload, _ = case
    kwargs = dict(expected_commit="a" * 40, trusted_key_id="test-key-1",
                  trusted_public_key_b64=b64(public))
    kwargs.update(overrides)
    return verify_attestation(attestation, artifact, **kwargs)


def test_valid_detached_attestation_passes(signed_case):
    assert verify(signed_case)["status"] == "VERIFIED"


@pytest.mark.parametrize("field,value", [
    ("trusted_key_id", None),
    ("trusted_public_key_b64", None),
    ("expected_commit", "b" * 40),
    ("trusted_key_id", "attacker-key"),
])
def test_missing_or_mismatched_external_trust_fails(signed_case, field, value):
    with pytest.raises(AttestationError):
        verify(signed_case, **{field: value})


def test_payload_tampering_breaks_signature(signed_case):
    attestation, artifact, public, payload, envelope = signed_case
    envelope["payload_b64"] = b64(b'{"schema_version":1}')
    attestation.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(AttestationError, match="signature"):
        verify(signed_case)


def test_artifact_tampering_breaks_digest(signed_case):
    _, artifact, _, _, _ = signed_case
    artifact.write_bytes(b"tampered")
    with pytest.raises(AttestationError, match="SHA-256"):
        verify(signed_case)


def test_signed_payload_with_non_https_source_is_rejected(signed_case):
    attestation, artifact, public, payload, _ = signed_case
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    # A fresh signer models an authorized signer issuing a malformed provenance payload.
    private = Ed25519PrivateKey.generate()
    pub = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    payload["source_url"] = "http://untrusted.example/"
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    envelope = {"schema_version": 1, "key_id": "test-key-1",
                "payload_b64": b64(payload_bytes), "signature_b64": b64(private.sign(payload_bytes))}
    attestation.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(AttestationError, match="HTTPS"):
        verify(signed_case, trusted_public_key_b64=b64(pub))
