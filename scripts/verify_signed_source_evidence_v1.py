#!/usr/bin/env python3
"""Fail-closed verifier for signed source-evidence envelopes.

Envelope fields: expected_commit, evidence_path, raw_sha256, source_url,
redirect_chain, retrieved_at, market_scope, key_id, payload_b64, signature_b64.
The Ed25519 signature covers canonical JSON of every field except signature_b64.
"""
import argparse, base64, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

def canonical_signed_bytes(envelope):
    signed = {k: v for k, v in envelope.items() if k != "signature_b64"}
    return json.dumps(signed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def require(condition, message):
    if not condition:
        raise ValueError(message)

def verify(envelope, *, expected_commit, expected_path, market_scope, key_registry,
           now=None, max_age_seconds=86400):
    require(isinstance(envelope, dict), "envelope must be an object")
    require(envelope.get("expected_commit") == expected_commit, "expected commit mismatch")
    require(envelope.get("evidence_path") == expected_path, "evidence path mismatch")
    require(envelope.get("market_scope") == market_scope, "market scope mismatch")
    digest = envelope.get("raw_sha256", "")
    require(isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "invalid raw SHA-256")
    url = envelope.get("source_url", "")
    require(urlparse(url).scheme == "https" and bool(urlparse(url).netloc), "source URL must be HTTPS")
    redirects = envelope.get("redirect_chain")
    require(isinstance(redirects, list) and redirects, "redirect chain missing")
    require(all(isinstance(u, str) and urlparse(u).scheme == "https" and urlparse(u).netloc for u in redirects), "invalid redirect URL")
    require(redirects[-1] == url, "redirect chain final URL differs from source URL")
    stamp = envelope.get("retrieved_at", "")
    try:
        retrieved = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        require(retrieved.tzinfo is not None, "retrieved_at must include timezone")
    except Exception as exc:
        raise ValueError("invalid retrieved_at") from exc
    now = now or datetime.now(timezone.utc)
    age = (now - retrieved.astimezone(timezone.utc)).total_seconds()
    require(age >= -60, "retrieval time is in the future")
    require(age <= max_age_seconds, "source signature/evidence is stale")
    key_id = envelope.get("key_id")
    require(isinstance(key_id, str) and key_id in key_registry, "untrusted key id")
    require(envelope.get("signature_algorithm") == "Ed25519", "unsupported signature algorithm")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pub = base64.b64decode(key_registry[key_id], validate=True)
        sig = base64.b64decode(envelope["signature_b64"], validate=True)
        payload = base64.b64decode(envelope["payload_b64"], validate=True)
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, canonical_signed_bytes(envelope))
    except Exception as exc:
        raise ValueError("signature verification failed") from exc
    require(hashlib.sha256(payload).hexdigest() == digest, "raw payload SHA-256 mismatch")
    return {"status": "VERIFIED", "expected_commit": expected_commit, "evidence_path": expected_path,
            "raw_sha256": digest, "source_url": url, "redirect_chain": redirects,
            "retrieved_at": stamp, "market_scope": market_scope, "key_id": key_id}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("envelope")
    p.add_argument("--expected-commit", required=True)
    p.add_argument("--expected-path", required=True)
    p.add_argument("--market-scope", required=True)
    p.add_argument("--key-registry", required=True, help="JSON object mapping key_id to base64 raw Ed25519 public key")
    p.add_argument("--max-age-seconds", type=int, default=86400)
    a = p.parse_args()
    try:
        result = verify(json.loads(Path(a.envelope).read_text()), expected_commit=a.expected_commit,
                        expected_path=a.expected_path, market_scope=a.market_scope,
                        key_registry=json.loads(Path(a.key_registry).read_text()),
                        max_age_seconds=a.max_age_seconds)
        print(json.dumps(result, sort_keys=True, indent=2))
    except Exception as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
