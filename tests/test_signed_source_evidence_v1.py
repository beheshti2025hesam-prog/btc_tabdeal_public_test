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
         "source_url": "https://docs.tabdeal.org/source",
         "redirect_chain": ["https://docs.tabdeal.org/redirect", "https://docs.tabdeal.org/source"],
         "retrieved_at": NOW.isoformat(), "market_scope": MARKET, "key_id": "test-key",
         "signature_algorithm": "Ed25519", "payload_b64": base64.b64encode(PAYLOAD).decode()}
    e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
    return e


class SignedSourceEvidenceTests(unittest.TestCase):
    def check(self, e):
        return verify(e, expected_commit=COMMIT, expected_path=PATH, market_scope=MARKET,
                      key_registry={"test-key": PUB}, now=NOW, max_age_seconds=3600)

    def test_valid_envelope(self):
        self.assertEqual(self.check(envelope())["status"], "VERIFIED")

    def test_wrong_commit_rejected_even_if_signed(self):
        e = envelope(); e["expected_commit"] = "b" * 40
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "commit mismatch"): self.check(e)

    def test_wrong_path_rejected_even_if_signed(self):
        e = envelope(); e["evidence_path"] = "evidence/other.json"
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "path mismatch"): self.check(e)

    def test_untrusted_key_rejected(self):
        e = envelope(); e["key_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "untrusted key"): self.check(e)

    def test_payload_tamper_rejected(self):
        e = envelope(); e["payload_b64"] = base64.b64encode(b"tampered").decode()
        with self.assertRaisesRegex(ValueError, "signature verification failed"): self.check(e)

    def test_forged_signature_rejected(self):
        e = envelope(); e["signature_b64"] = base64.b64encode(b"x" * 64).decode()
        with self.assertRaisesRegex(ValueError, "signature verification failed"): self.check(e)

    def test_expired_evidence_rejected(self):
        e = envelope(); e["retrieved_at"] = "2026-10-12T00:00:00+00:00"
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "stale"): self.check(e)

    def test_redirect_chain_identity_required(self):
        e = envelope(); e["redirect_chain"] = ["https://docs.tabdeal.org/other"]
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "final URL"): self.check(e)

    def test_market_scope_mismatch_rejected(self):
        e = envelope(); e["market_scope"] = "other-venue"
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "market scope"): self.check(e)

    def test_unsafe_evidence_paths_rejected_even_when_signed(self):
        for unsafe_path in ("../outside.json", "/tmp/evidence.json", "evidence\\\\outside.json", "evidence//source.json", "C:/evidence.json"):
            with self.subTest(path=unsafe_path):
                e = envelope()
                e["evidence_path"] = unsafe_path
                e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
                with self.assertRaisesRegex(ValueError, "unsafe evidence path|canonical"):
                    verify(e, expected_commit=COMMIT, expected_path=unsafe_path,
                           market_scope=MARKET, key_registry={"test-key": PUB},
                           now=NOW, max_age_seconds=3600)

    def test_malformed_source_port_rejected(self):
        e = envelope()
        e["source_url"] = "https://docs.tabdeal.org:bad/source"
        e["redirect_chain"] = [e["source_url"]]
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "invalid source URL"):
            self.check(e)

    def test_source_url_credentials_rejected_even_when_signed(self):
        e = envelope()
        e["source_url"] = "https://trusted.example@evil.example/source"
        e["redirect_chain"] = [e["source_url"]]
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "must not contain credentials"):
            self.check(e)

    def test_source_url_fragment_rejected_even_when_signed(self):
        e = envelope()
        e["source_url"] = "https://docs.tabdeal.org/source#fragment"
        e["redirect_chain"] = [e["source_url"]]
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "must not contain a fragment"):
            self.check(e)

    def test_redirect_credentials_rejected_even_when_signed(self):
        e = envelope()
        e["redirect_chain"] = ["https://user:secret@exchange.example/redirect", e["source_url"]]
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "must not contain credentials"):
            self.check(e)

    def test_source_domain_allowlist_rejects_untrusted_host_even_when_signed(self):
        e = envelope()
        e["source_url"] = "https://evil.example/source"
        e["redirect_chain"] = [e["source_url"]]
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "host is not allowlisted"):
            self.check(e)

    def test_redirect_domain_allowlist_rejects_untrusted_hop_even_when_signed(self):
        e = envelope()
        e["redirect_chain"] = ["https://evil.example/redirect", e["source_url"]]
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "host is not allowlisted"):
            self.check(e)

    def test_redirect_chain_rejects_loop(self):
        e = envelope()
        e["redirect_chain"] = ["https://docs.tabdeal.org/source", "https://docs.tabdeal.org/source"]
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "redirect chain contains a loop"):
            self.check(e)

    def test_nonstandard_https_port_rejected(self):
        e = envelope()
        e["source_url"] = "https://docs.tabdeal.org:8443/source"
        e["redirect_chain"] = [e["source_url"]]
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "non-standard source URL port"):
            self.check(e)

    def test_source_url_whitespace_rejected_even_when_signed(self):
        e = envelope()
        e["source_url"] = "https://docs.tabdeal.org/bad path"
        e["redirect_chain"] = [e["source_url"]]
        e["signature_b64"] = base64.b64encode(KEY.sign(canonical_signed_bytes(e))).decode()
        with self.assertRaisesRegex(ValueError, "invalid source URL"):
            self.check(e)


if __name__ == "__main__":
    unittest.main()
