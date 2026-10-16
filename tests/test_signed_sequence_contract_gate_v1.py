import base64
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone

from pathlib import Path
from unittest.mock import patch

from forward.signed_sequence_contract_gate_v1 import verify_sequence_contract_evidence, validate_sequence_contract_payload
from scripts.verify_signed_source_evidence_v1 import verify


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


    def test_unknown_or_revoked_key_id_fails_closed(self):
        now = datetime.now(timezone.utc)
        source_url = "https://docs.tabdeal.org/evidence"
        final_headers = b"Content-Type:application/json\r\n\r\n"
        envelope = {
            "expected_commit": "a" * 40,
            "evidence_path": "evidence/sequence.json",
            "raw_sha256": "0" * 64,
            "source_url": source_url,
            "redirect_chain": [source_url],
            "redirect_evidence_schema": "hes_http_redirect_hops_v1",
            "initial_request_url": source_url,
            "redirect_hops": [],
            "final_response": {
                "url": source_url,
                "response_status": 200,
                "response_headers_b64": base64.b64encode(final_headers).decode("ascii"),
                "response_headers_sha256": hashlib.sha256(final_headers).hexdigest(),
            },
            "retrieved_at": now.isoformat(),
            "market_scope": "tabdeal:spot:BTC_USDT",
            "key_id": "revoked-or-unknown-key",
            "signature_algorithm": "Ed25519",
            "payload_b64": "",
            "signature_b64": "",
        }
        with self.assertRaisesRegex(ValueError, "untrusted key id"):
            verify(
                envelope,
                expected_commit="a" * 40,
                expected_path="evidence/sequence.json",
                market_scope="tabdeal:spot:BTC_USDT",
                key_registry={},
                now=now,
            )

    def test_registry_rollback_to_old_bytes_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            envelope = root / "envelope.json"
            registry = root / "keys.json"
            envelope.write_text("{}", encoding="utf-8")
            old_registry_bytes = json.dumps({"old-key": "b2xk"}).encode("utf-8")
            current_registry_bytes = json.dumps({"current-key": "Y3VycmVudA=="}).encode("utf-8")
            # The trusted pin represents the current registry version, not the old version.
            registry.write_bytes(old_registry_bytes)
            trusted_current_digest = hashlib.sha256(current_registry_bytes).hexdigest()
            with self.assertRaisesRegex(ValueError, "registry identity mismatch"):
                verify_sequence_contract_evidence(
                    envelope_path=envelope,
                    key_registry_path=registry,
                    expected_commit="a" * 40,
                    expected_evidence_path="evidence/sequence.json",
                    market_scope="tabdeal:spot:BTC_USDT",
                    trusted_key_registry_sha256=trusted_current_digest,
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


    def test_contract_structure_requires_exact_scope_and_capability_schema(self):
        payload = {
            "schema": "hes_sequence_contract_v1",
            "venue": "tabdeal",
            "product": "futures_margin",
            "endpoint": "special_margin/broadcast/",
            "channel": "trade_broadcast",
            "message_type": "trade",
            "field_path": "trade.sequence",
            "scope": "tabdeal:futures:BTC_USDT",
            "protocol_version": "unknown",
            "semantic_class": "unknown",
            "capabilities": {
                "exact_replay_dedup": True,
                "event_id_dedup": False,
                "ordered_within_scope": False,
                "contiguous_within_scope": False,
                "gap_detectable": False,
                "cross_reconnect": False,
            },
        }
        result = validate_sequence_contract_payload(
            json.dumps(payload).encode(), market_scope="tabdeal:futures:BTC_USDT"
        )
        assert result["capabilities"]["ordered_within_scope"] is False
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            validate_sequence_contract_payload(
                json.dumps(payload).encode(), market_scope="tabdeal:spot:BTC_USDT"
            )

    def test_contract_rejects_implied_capability_without_prerequisite(self):
        payload = {
            "schema": "hes_sequence_contract_v1",
            "venue": "tabdeal",
            "product": "futures_margin",
            "endpoint": "special_margin/broadcast/",
            "channel": "trade_broadcast",
            "message_type": "trade",
            "field_path": "trade.sequence",
            "scope": "tabdeal:futures:BTC_USDT",
            "protocol_version": "unknown",
            "semantic_class": "unknown",
            "capabilities": {
                "exact_replay_dedup": False,
                "event_id_dedup": False,
                "ordered_within_scope": False,
                "contiguous_within_scope": True,
                "gap_detectable": False,
                "cross_reconnect": False,
            },
        }
        with self.assertRaisesRegex(ValueError, "requires ordered capability"):
            validate_sequence_contract_payload(
                json.dumps(payload).encode(), market_scope="tabdeal:futures:BTC_USDT"
            )


if __name__ == "__main__":
    unittest.main()
