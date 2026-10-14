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
