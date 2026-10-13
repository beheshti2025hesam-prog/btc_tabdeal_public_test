import base64
import hashlib
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from hes_attestation.contract import AttestationError, canonical_payload, verify_attestation


class AttestationContractTests(unittest.TestCase):
    def setUp(self):
        self.artifact = b"evidence artifact: deterministic test bytes\n"
        self.private = Ed25519PrivateKey.generate()
        self.public = self.private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.key_id = "test-key-out-of-band"
        self.attestation = {
            "schema": "hes.evidence_attestation.v1",
            "artifact_path": "evidence/test-artifact.json",
            "artifact_sha256": hashlib.sha256(self.artifact).hexdigest(),
            "artifact_bytes": len(self.artifact),
            "commit_sha": "c3f35dbdc443e4c651e68eb8a1092f2d13406cb8",
            "signer_key_id": self.key_id,
            "signature_algorithm": "Ed25519",
            "signature": "",
        }
        self.attestation["signature"] = base64.b64encode(
            self.private.sign(canonical_payload(self.attestation))
        ).decode("ascii")

    def test_positive_valid_artifact_and_signature(self):
        self.assertTrue(verify_attestation(
            self.attestation, self.artifact, self.key_id, self.public
        ))

    def test_negative_forged_signature(self):
        forged = dict(self.attestation)
        forged["signature"] = base64.b64encode(b"\x00" * 64).decode("ascii")
        with self.assertRaisesRegex(AttestationError, "signature verification failed"):
            verify_attestation(forged, self.artifact, self.key_id, self.public)

    def test_negative_hash_mismatch(self):
        with self.assertRaisesRegex(AttestationError, "SHA-256 mismatch"):
            verify_attestation(
                self.attestation, self.artifact + b"tampered", self.key_id, self.public
            )

    def test_negative_incomplete_contract(self):
        incomplete = dict(self.attestation)
        del incomplete["commit_sha"]
        with self.assertRaisesRegex(AttestationError, "missing fields"):
            verify_attestation(incomplete, self.artifact, self.key_id, self.public)

    def test_negative_untrusted_key_id(self):
        with self.assertRaisesRegex(AttestationError, "untrusted signer_key_id"):
            verify_attestation(self.attestation, self.artifact, "key-from-pr", self.public)

    def test_negative_artifact_length_mismatch(self):
        with self.assertRaisesRegex(AttestationError, "byte length mismatch"):
            verify_attestation(
                self.attestation, self.artifact + b"x", self.key_id, self.public
            )

    def test_negative_extra_field_rejected(self):
        extra = dict(self.attestation, executor_override=True)
        with self.assertRaisesRegex(AttestationError, "unexpected fields"):
            verify_attestation(extra, self.artifact, self.key_id, self.public)


if __name__ == "__main__":
    unittest.main()
