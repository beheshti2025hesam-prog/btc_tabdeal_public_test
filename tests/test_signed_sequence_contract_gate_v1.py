import base64
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from scripts.verify_signed_source_evidence_v1 import canonical_signed_bytes
from pathlib import Path
from unittest.mock import patch

from forward.signed_sequence_contract_gate_v1 import verify_sequence_contract_evidence


class SignedSequenceContractGateTests(unittest.TestCase):
    # This literal models a registry digest provisioned independently of the
    # workspace. Never derive the trusted pin from the registry under test.
    TRUSTED_REGISTRY_SHA256 = "5659ba7e82b4eaa8fa8c3f3feb790b271647c87ab4c168cc4bf8a60924602c1a"

    def test_missing_envelope_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = root / "keys.json"
            registry.write_text(json.dumps({"test": "ZmFrZQ=="}), encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                verify_sequence_contract_evidence(
                    envelope_path=root / "missing.json",
                    key_registry_path=registry,
                    expected_commit="a" * 40,
                    expected_evidence_path="evidence/sequence.json",
                    market_scope="tabdeal:spot:BTC_USDT",
                )

    def test_empty_trust_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"HES_TRUSTED_KEY_REGISTRY_SHA256": self.TRUSTED_REGISTRY_SHA256},
            clear=True,
        ):
            root = Path(tmp)
            envelope = root / "envelope.json"
            registry = root / "keys.json"
            envelope.write_text("{}", encoding="utf-8")
            registry.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "trusted key-registry SHA-256 mismatch"):
                verify_sequence_contract_evidence(
                    envelope_path=envelope,
                    key_registry_path=registry,
                    expected_commit="a" * 40,
                    expected_evidence_path="evidence/sequence.json",
                    market_scope="tabdeal:spot:BTC_USDT",
                )

    def test_missing_independent_registry_pin_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp)
            envelope = root / "envelope.json"
            registry = root / "keys.json"
            envelope.write_text("{}", encoding="utf-8")
            registry.write_text(json.dumps({"attacker": "ZmFrZQ=="}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "independent trusted key-registry"):
                verify_sequence_contract_evidence(
                    envelope_path=envelope,
                    key_registry_path=registry,
                    expected_commit="a" * 40,
                    expected_evidence_path="evidence/sequence.json",
                    market_scope="tabdeal:spot:BTC_USDT",
                )

    def test_coordinated_registry_and_envelope_replacement_fails_against_independent_pin(self):
        """Replacing both caller-supplied files must not replace the trust anchor."""
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"HES_TRUSTED_KEY_REGISTRY_SHA256": self.TRUSTED_REGISTRY_SHA256},
            clear=True,
        ):
            root = Path(tmp)
            envelope = root / "envelope.json"
            registry = root / "keys.json"

            # Simulate an attacker who controls both workspace artifacts and
            # installs their own key plus an envelope claiming that key.
            attacker_private_key = Ed25519PrivateKey.generate()
            attacker_public_key = base64.b64encode(
                attacker_private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            ).decode("ascii")
            registry.write_text(
                json.dumps({"attacker-controlled-key": attacker_public_key}, separators=(",", ":")),
                encoding="utf-8",
            )
            attacker_claim = {
                "key_id": "attacker-controlled-key",
                "signature_algorithm": "Ed25519",
                "sequence_contract": {
                    "status": "verified",
                    "capabilities": {
                        "unique": True,
                        "ordered": True,
                        "contiguous": True,
                        "comparable_across_reconnect": False,
                    },
                },
                "claim": "attacker-controlled envelope; not authoritative evidence",
            }
            envelope.write_text(json.dumps(attacker_claim), encoding="utf-8")

            # The registry's actual digest differs from the independently
            # pinned trusted registry. Rejection must happen before the
            # attacker-controlled envelope can confer authority.
            with self.assertRaisesRegex(ValueError, "trusted key-registry SHA-256 mismatch"):
                verify_sequence_contract_evidence(
                    envelope_path=envelope,
                    key_registry_path=registry,
                    expected_commit="a" * 40,
                    expected_evidence_path="evidence/sequence.json",
                    market_scope="tabdeal:futures:BTC_USDT",
                )

    def test_signed_arbitrary_payload_is_not_a_sequence_contract(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp)
            payload = b'{"sequence_contract":"signed-but-insufficient"}'
            source_url = "https://docs.tabdeal.org/"
            now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
            private_key = Ed25519PrivateKey.generate()
            public_key = base64.b64encode(
                private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            ).decode("ascii")
            envelope = {
                "expected_commit": "a" * 40,
                "evidence_path": "evidence/sequence.json",
                "raw_sha256": hashlib.sha256(payload).hexdigest(),
                "source_url": source_url,
                "redirect_chain": [source_url],
                "retrieved_at": now.isoformat(),
                "market_scope": "tabdeal:futures:BTC_USDT",
                "key_id": "synthetic-test-key",
                "signature_algorithm": "Ed25519",
                "payload_b64": base64.b64encode(payload).decode("ascii"),
            }
            envelope["signature_b64"] = base64.b64encode(
                private_key.sign(canonical_signed_bytes(envelope))
            ).decode("ascii")
            envelope_path = root / "envelope.json"
            registry_path = root / "keys.json"
            envelope_path.write_text(json.dumps(envelope), encoding="utf-8")
            registry_path.write_text(
                json.dumps({"synthetic-test-key": public_key}), encoding="utf-8"
            )
            os.environ["HES_TRUSTED_KEY_REGISTRY_SHA256"] = hashlib.sha256(
                registry_path.read_bytes()
            ).hexdigest()
            with self.assertRaisesRegex(ValueError, "missing or unexpected fields"):
                verify_sequence_contract_evidence(
                    envelope_path=envelope_path,
                    key_registry_path=registry_path,
                    expected_commit="a" * 40,
                    expected_evidence_path="evidence/sequence.json",
                    market_scope="tabdeal:futures:BTC_USDT",
                    max_age_seconds=3600,
                    now=now,
                )


if __name__ == "__main__":
    unittest.main()
