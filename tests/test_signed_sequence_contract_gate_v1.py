import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forward.signed_sequence_contract_gate_v1 import verify_sequence_contract_evidence


class SignedSequenceContractGateTests(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            envelope = root / "envelope.json"
            registry = root / "keys.json"
            envelope.write_text("{}", encoding="utf-8")
            registry.write_text("{}", encoding="utf-8")
            os.environ["HES_TRUSTED_KEY_REGISTRY_SHA256"] = hashlib.sha256(registry.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "non-empty"):
                verify_sequence_contract_evidence(
                    envelope_path=envelope,
                    key_registry_path=registry,
                    expected_commit="a" * 40,
                    expected_evidence_path="evidence/sequence.json",
                    market_scope="tabdeal:spot:BTC_USDT",
                )


    def test_coordinated_registry_replacement_rejected_by_independent_pin(self):
        """Replacing the registry cannot redefine the independently pinned digest."""
        trusted_registry_bytes = b'{"trusted-test-key":"dHJ1c3RlZA=="}'
        independent_pin = hashlib.sha256(trusted_registry_bytes).hexdigest()
        attacker_registry_bytes = b'{"attacker-controlled-key":"ZmFrZQ=="}'

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {"HES_TRUSTED_KEY_REGISTRY_SHA256": independent_pin},
            clear=True,
        ):
            root = Path(tmp)
            envelope = root / "envelope.json"
            registry = root / "keys.json"
            # The envelope and registry are attacker-controlled together.
            envelope.write_text("{}", encoding="utf-8")
            registry.write_bytes(attacker_registry_bytes)

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


if __name__ == "__main__":
    unittest.main()
