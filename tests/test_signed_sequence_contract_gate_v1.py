import hashlib
import json
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
                    trusted_key_registry_sha256=hashlib.sha256(registry.read_bytes()).hexdigest(),
                )


    def test_registry_replacement_with_attacker_key_is_rejected_before_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            envelope = root / "envelope.json"
            registry = root / "keys.json"
            envelope.write_text("{}", encoding="utf-8")
            registry.write_text(json.dumps({"trusted": "ZmFrZQ=="}), encoding="utf-8")
            independently_pinned_digest = hashlib.sha256(registry.read_bytes()).hexdigest()
            # Attacker replaces the entire registry and inserts their own key.
            registry.write_text(json.dumps({"attacker": "YWNrZXI="}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "registry identity mismatch"):
                verify_sequence_contract_evidence(
                    envelope_path=envelope,
                    key_registry_path=registry,
                    expected_commit="a" * 40,
                    expected_evidence_path="evidence/sequence.json",
                    market_scope="tabdeal:spot:BTC_USDT",
                    trusted_key_registry_sha256=independently_pinned_digest,
                )

    def test_empty_trust_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            envelope = root / "envelope.json"
            registry = root / "keys.json"
            envelope.write_text("{}", encoding="utf-8")
            registry.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-empty"):
                verify_sequence_contract_evidence(
                    envelope_path=envelope,
                    key_registry_path=registry,
                    expected_commit="a" * 40,
                    expected_evidence_path="evidence/sequence.json",
                    market_scope="tabdeal:spot:BTC_USDT",
                    trusted_key_registry_sha256=hashlib.sha256(registry.read_bytes()).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
