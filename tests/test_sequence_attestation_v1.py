import base64

import pytest

from forward.sequence_attestation_v1 import AttestationError, verify_registry_attestation


def test_attestation_fails_closed_when_external_key_is_missing(monkeypatch):
    monkeypatch.delenv("HES_SEQUENCE_TRUSTED_PUBLIC_KEY_PEM", raising=False)
    with pytest.raises(AttestationError, match="TRUSTED_PUBLIC_KEY_MISSING"):
        verify_registry_attestation(b"registry bytes", {
            "registry_signature_ed25519_b64": base64.b64encode(b"x" * 64).decode()
        })


def test_attestation_fails_closed_when_signature_is_missing(monkeypatch):
    monkeypatch.setenv("HES_SEQUENCE_TRUSTED_PUBLIC_KEY_PEM", "not used without signature")
    with pytest.raises(AttestationError, match="REGISTRY_SIGNATURE_MISSING"):
        verify_registry_attestation(b"registry bytes", {})


def test_attestation_rejects_malformed_signature_encoding(monkeypatch):
    monkeypatch.setenv("HES_SEQUENCE_TRUSTED_PUBLIC_KEY_PEM", "not a valid key")
    with pytest.raises(AttestationError, match="REGISTRY_SIGNATURE_ENCODING_INVALID"):
        verify_registry_attestation(b"registry bytes", {
            "registry_signature_ed25519_b64": "not base64!"
        })


def test_attestation_rejects_wrong_signature_length(monkeypatch):
    monkeypatch.setenv("HES_SEQUENCE_TRUSTED_PUBLIC_KEY_PEM", "not used for malformed signature")
    with pytest.raises(AttestationError, match="REGISTRY_SIGNATURE_LENGTH_INVALID"):
        verify_registry_attestation(b"registry bytes", {
            "registry_signature_ed25519_b64": base64.b64encode(b"short").decode()
        })


import subprocess
from pathlib import Path


def _make_ed25519_keypair(tmp_path: Path, stem: str):
    private_key = tmp_path / f"{stem}-private.pem"
    public_key = tmp_path / f"{stem}-public.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
        check=True, capture_output=True, timeout=5,
    )
    subprocess.run(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True, capture_output=True, timeout=5,
    )
    return private_key, public_key


def _sign(private_key: Path, payload: Path, signature: Path):
    subprocess.run(
        ["openssl", "pkeyutl", "-sign", "-inkey", str(private_key), "-rawin",
         "-in", str(payload), "-out", str(signature)],
        check=True, capture_output=True, timeout=5,
    )


def test_valid_external_ed25519_attestation_is_accepted(monkeypatch, tmp_path):
    private_key, public_key = _make_ed25519_keypair(tmp_path, "trusted")
    payload = tmp_path / "registry.bin"
    payload.write_bytes(b"exact registry bytes")
    signature = tmp_path / "registry.sig"
    _sign(private_key, payload, signature)
    monkeypatch.setenv("HES_SEQUENCE_TRUSTED_PUBLIC_KEY_PEM", public_key.read_text())
    verify_registry_attestation(payload.read_bytes(), {
        "registry_signature_ed25519_b64": base64.b64encode(signature.read_bytes()).decode()
    })


def test_registry_tampering_invalidates_signature(monkeypatch, tmp_path):
    private_key, public_key = _make_ed25519_keypair(tmp_path, "trusted")
    payload = tmp_path / "registry.bin"
    payload.write_bytes(b"original registry")
    signature = tmp_path / "registry.sig"
    _sign(private_key, payload, signature)
    monkeypatch.setenv("HES_SEQUENCE_TRUSTED_PUBLIC_KEY_PEM", public_key.read_text())
    with pytest.raises(AttestationError, match="REGISTRY_SIGNATURE_INVALID"):
        verify_registry_attestation(b"tampered registry", {
            "registry_signature_ed25519_b64": base64.b64encode(signature.read_bytes()).decode()
        })


def test_signature_from_unknown_key_is_rejected(monkeypatch, tmp_path):
    signing_key, _ = _make_ed25519_keypair(tmp_path, "attacker")
    _, trusted_public_key = _make_ed25519_keypair(tmp_path, "trusted")
    payload = tmp_path / "registry.bin"
    payload.write_bytes(b"registry bytes")
    signature = tmp_path / "registry.sig"
    _sign(signing_key, payload, signature)
    monkeypatch.setenv("HES_SEQUENCE_TRUSTED_PUBLIC_KEY_PEM", trusted_public_key.read_text())
    with pytest.raises(AttestationError, match="REGISTRY_SIGNATURE_INVALID"):
        verify_registry_attestation(payload.read_bytes(), {
            "registry_signature_ed25519_b64": base64.b64encode(signature.read_bytes()).decode()
        })
