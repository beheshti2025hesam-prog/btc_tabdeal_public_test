import base64
import hashlib
import json

import pytest

from scripts.independent_source_attestor_v1 import (
    _validate_url,
    canonical_payload,
    retrieve_and_attest,
)
from forward.source_attestation_verifier_v1 import verify_attestation, AttestationError

cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def test_url_validation_requires_exact_allowlisted_https_host():
    _validate_url("https://docs.tabdeal.org/", {"docs.tabdeal.org"})
    for url in (
        "http://docs.tabdeal.org/",
        "https://docs.tabdeal.org.attacker.example/",
        "https://user:pass@docs.tabdeal.org/",
        "https://docs.tabdeal.org:444/",
    ):
        with pytest.raises(ValueError):
            _validate_url(url, {"docs.tabdeal.org"})


def test_missing_independent_signing_key_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("HES_SOURCE_ATTESTATION_PRIVATE_KEY_B64", raising=False)
    monkeypatch.delenv("HES_SOURCE_ATTESTATION_KEY_ID", raising=False)
    with pytest.raises(ValueError, match="signing key"):
        retrieve_and_attest(
            url="https://docs.tabdeal.org/", allowed_hosts={"docs.tabdeal.org"},
            context={"venue": "tabdeal"}, snapshot_path=tmp_path / "raw.bin",
            attestation_path=tmp_path / "attestation.json",
        )


def test_canonical_payload_excludes_signature_and_is_stable():
    a = {"b": 2, "a": 1, "signature": "ignored"}
    b = {"a": 1, "b": 2, "signature": "different"}
    assert canonical_payload(a) == canonical_payload(b)


def test_signed_attestation_schema_is_compatible_with_verifier(tmp_path, monkeypatch):
    # Synthetic bytes only test format compatibility; this is NOT production provenance.
    raw = b"synthetic raw source bytes"
    snapshot = tmp_path / "source.bin"
    snapshot.write_bytes(raw)
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    context = {"venue": "tabdeal", "product": "fapi-futures-margin"}
    att = {
        "schema_version": "hes-source-attestation-v1",
        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "requested_url": "https://docs.tabdeal.org/",
        "final_url": "https://docs.tabdeal.org/",
        "redirect_chain": [{"url": "https://docs.tabdeal.org/", "status": 200}],
        "retrieved_at_utc": "2026-10-12T00:00:00Z",
        "retrieval_tool": "hes-independent-source-attestor",
        "retrieval_tool_version": "1.0.0",
        "source_context": context,
        "signer_key_id": "isolated-test-key",
    }
    att["signature"] = base64.b64encode(private.sign(canonical_payload(att))).decode("ascii")
    att_path = tmp_path / "attestation.json"
    att_path.write_text(json.dumps(att), encoding="utf-8")
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_PUBLIC_KEY_B64", base64.b64encode(public).decode("ascii"))
    monkeypatch.setenv("HES_SOURCE_ATTESTATION_KEY_ID", "isolated-test-key")
    result = verify_attestation(
        snapshot_path=snapshot, attestation_path=att_path,
        expected_context=context,
    )
    assert result["verified"] is True
    assert result["snapshot_sha256"] == hashlib.sha256(raw).hexdigest()
