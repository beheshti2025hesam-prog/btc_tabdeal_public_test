import base64, hashlib, unittest
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from scripts.verify_signed_source_evidence_v1 import canonical_signed_bytes, verify

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
COMMIT = "a" * 40
PATH = "evidence/source.json"
MARKET = "tabdeal:spot:BTC_USDT"
PAYLOAD = b'{"evidence":"raw-bytes"}'
KEY = Ed25519PrivateKey.generate()
PUB = base64.b64encode(KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()

def envelope():
    e = {"expected_commit": COMMIT, "evidence_path": PATH,
         "raw_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
         "requested_url": "https://exchange.example/start",
         "source_url": "https://exchange.example/source",
         "redirect_chain": ["https://exchange.example/start", "https://exchange.example/source"],
         "retrieved_at": NOW.isoformat(), "market_scope": MARKET, "key_id": "test-key",
         "signature_algorithm": "Ed25519", "payload_b64": base64.b64encode(PAYLOAD).decode()}
    e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
    return e

def resign(e):
    e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
    return e

class SignedSourceEvidenceTests(unittest.TestCase):
    def check(self, e, **kwargs):
        args = {"expected_commit": COMMIT, "expected_path": PATH, "market_scope": MARKET,
                "key_registry": {"test-key": PUB}, "now": NOW, "max_age_seconds": 3600}
        args.update(kwargs)
        return verify(e, **args)
    def test_valid_envelope(self):
        self.assertEqual(self.check(envelope())["status"], "VERIFIED")
    def test_wrong_commit_rejected_even_if_signed(self):
        e = envelope(); e["expected_commit"] = "b" * 40; resign(e)
        with self.assertRaisesRegex(ValueError, "commit mismatch"): self.check(e)
    def test_malformed_expected_commit_rejected(self):
        with self.assertRaisesRegex(ValueError, "full hexadecimal Git SHA"):
            self.check(envelope(), expected_commit="not-a-sha")
    def test_wrong_path_rejected_even_if_signed(self):
        e = envelope(); e["evidence_path"] = "evidence/other.json"; resign(e)
        with self.assertRaisesRegex(ValueError, "path mismatch"): self.check(e)
    def test_path_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsafe evidence path"):
            self.check(envelope(), expected_path="../evidence/source.json")
    def test_untrusted_key_rejected(self):
        e = envelope(); e["key_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "untrusted key"): self.check(e)
    def test_payload_tamper_rejected(self):
        e = envelope(); e["payload_b64"] = base64.b64encode(b"tampered").decode()
        with self.assertRaisesRegex(ValueError, "signature verification failed"): self.check(e)
    def test_signed_wrong_raw_digest_rejected(self):
        e = envelope(); e["raw_sha256"] = "0" * 64; resign(e)
        with self.assertRaisesRegex(ValueError, "raw payload SHA-256 mismatch"): self.check(e)
    def test_forged_signature_rejected(self):
        e = envelope(); e["signature_b64"] = base64.b64encode(b"x" * 64).decode()
        with self.assertRaisesRegex(ValueError, "signature verification failed"): self.check(e)
    def test_expired_evidence_rejected(self):
        e = envelope(); e["retrieved_at"] = "2026-10-12T00:00:00+00:00"; resign(e)
        with self.assertRaisesRegex(ValueError, "stale"): self.check(e)
    def test_redirect_chain_initial_url_required(self):
        e = envelope(); e["redirect_chain"][0] = "https://evil.example/start"; resign(e)
        with self.assertRaisesRegex(ValueError, "initial URL"): self.check(e)
    def test_redirect_chain_final_url_required(self):
        e = envelope(); e["redirect_chain"][-1] = "https://evil.example/source"; resign(e)
        with self.assertRaisesRegex(ValueError, "final URL"): self.check(e)
    def test_market_scope_mismatch_rejected(self):
        e = envelope(); e["market_scope"] = "other-venue"; resign(e)
        with self.assertRaisesRegex(ValueError, "market scope"): self.check(e)
    def test_future_evidence_rejected(self):
        e = envelope(); e["retrieved_at"] = "2026-10-13T12:02:00+00:00"; resign(e)
        with self.assertRaisesRegex(ValueError, "future"): self.check(e)

if __name__ == "__main__": unittest.main()
