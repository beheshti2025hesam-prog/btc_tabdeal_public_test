#!/usr/bin/env python3
"""Fail-closed verifier for signed source-evidence envelopes.

Envelope fields: expected_commit, evidence_path, raw_sha256, source_url,
redirect_chain, retrieved_at, market_scope, key_id, payload_b64, signature_b64.
The Ed25519 signature covers canonical JSON of every field except signature_b64.
"""
import argparse, base64, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse, urljoin

# This evidence contract currently authorizes only the official Tabdeal docs host.
# Add other venues only through an independently reviewed, explicit trust-policy change.
TRUSTED_SOURCE_HOSTS = frozenset({"docs.tabdeal.org"})
MAX_REDIRECT_CHAIN_URLS = 11  # initial URL plus at most ten redirects
REDIRECT_EVIDENCE_SCHEMA = "hes_http_redirect_hops_v1"
ALLOWED_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def canonical_signed_bytes(envelope):
    signed = {k: v for k, v in envelope.items() if k != "signature_b64"}
    return json.dumps(signed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_evidence_path(path):
    # Evidence identifiers are repository-relative POSIX paths, never filesystem paths.
    require(isinstance(path, str) and bool(path), "evidence path must be a non-empty string")
    require("\\" not in path and "\x00" not in path, "unsafe evidence path")
    parsed = PurePosixPath(path)
    require(not parsed.is_absolute(), "unsafe evidence path")
    require(path == parsed.as_posix(), "evidence path must be canonical")
    require(all(part not in ("", ".", "..") for part in path.split("/")), "unsafe evidence path")
    require(not (len(path) >= 2 and path[1] == ":"), "unsafe evidence path")
    return path


def validate_https_url(value, *, label):
    """Reject ambiguous or credential-bearing HTTPS URLs before trusting signed metadata."""
    require(isinstance(value, str) and bool(value), f"{label} must be a non-empty HTTPS URL")
    require(not any(ord(ch) < 0x20 or ch.isspace() for ch in value), f"invalid {label}")
    require("\\" not in value, f"invalid {label}")
    parsed = urlparse(value)
    require(parsed.scheme == "https" and bool(parsed.netloc) and bool(parsed.hostname),
            f"{label} must be HTTPS")
    require(parsed.username is None and parsed.password is None, f"{label} must not contain credentials")
    require(not parsed.fragment, f"{label} must not contain a fragment")
    try:
        port = parsed.port  # Force malformed ports to fail closed.
    except ValueError as exc:
        raise ValueError(f"invalid {label}") from exc
    require(port is None or 1 <= port <= 65535, f"invalid {label} port")
    hostname = parsed.hostname.lower()
    require(hostname == hostname.rstrip("."), f"non-canonical {label} host")
    require(hostname in TRUSTED_SOURCE_HOSTS, f"{label} host is not allowlisted")
    require(port is None or port == 443, f"non-standard {label} port")
    return parsed



def _decode_header_block(encoded, expected_digest, *, label):
    require(isinstance(encoded, str) and encoded, f"{label} header evidence missing")
    require(isinstance(expected_digest, str) and len(expected_digest) == 64
            and all(ch in "0123456789abcdef" for ch in expected_digest),
            f"invalid {label} header SHA-256")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError(f"invalid {label} header evidence encoding") from exc
    require(hashlib.sha256(raw).hexdigest() == expected_digest,
            f"{label} header evidence digest mismatch")
    require(raw.endswith(b"\\r\\n\\r\\n"), f"{label} header block is not CRLF terminated")
    require(b"\\x00" not in raw and b"\\n" not in raw.replace(b"\\r\\n", b""),
            f"invalid {label} header block line endings")
    lines = raw[:-4].split(b"\\r\\n") if raw[:-4] else []
    parsed = []
    for line in lines:
        require(b":" in line and not line.startswith((b" ", b"\\t")),
                f"invalid {label} header line")
        name, value = line.split(b":", 1)
        require(name and all(ch in b"!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz" for ch in name),
                f"invalid {label} header name")
        parsed.append((name.decode("ascii").lower(), value.decode("latin-1")))
    return parsed


def validate_redirect_hop_evidence(envelope, source_url, redirects):
    """Validate signed, byte-bound HTTP response-header observations for every hop."""
    require(envelope.get("redirect_evidence_schema") == REDIRECT_EVIDENCE_SCHEMA,
            "redirect hop evidence schema missing or unsupported")
    require(envelope.get("initial_request_url") == redirects[0],
            "redirect initial request URL mismatch")
    hops = envelope.get("redirect_hops")
    require(isinstance(hops, list), "redirect hop evidence missing")
    require(len(hops) == len(redirects) - 1,
            "redirect hop evidence count mismatch")
    for index, hop in enumerate(hops):
        require(isinstance(hop, dict), "redirect hop must be an object")
        request_url = redirects[index]
        next_url = redirects[index + 1]
        require(hop.get("request_url") == request_url,
                "redirect hop request URL mismatch")
        require(hop.get("next_url") == next_url,
                "redirect hop next URL mismatch")
        status = hop.get("response_status")
        require(type(status) is int and status in ALLOWED_REDIRECT_STATUSES,
                "redirect hop status is not an allowed redirect")
        headers = _decode_header_block(
            hop.get("response_headers_b64"), hop.get("response_headers_sha256"),
            label=f"redirect hop {index} response",
        )
        locations = [value for name, value in headers if name == "location"]
        require(len(locations) == 1, "redirect hop must contain exactly one Location header")
        raw_location = hop.get("location_header")
        require(isinstance(raw_location, str) and raw_location == locations[0],
                "redirect hop raw Location value mismatch")
        require(not any(ord(ch) < 0x20 and ch != "\\t" for ch in raw_location),
                "redirect hop Location contains control characters")
        try:
            resolved = urljoin(request_url, raw_location)
        except Exception as exc:
            raise ValueError("redirect hop Location cannot be resolved") from exc
        require(resolved == next_url, "redirect hop resolved Location mismatch")
        parsed_request = validate_https_url(request_url, label="redirect request URL")
        parsed_next = validate_https_url(next_url, label="redirect next URL")
        require(parsed_request.hostname.lower() == parsed_next.hostname.lower(),
                "redirect hop host continuity violation")

    final = envelope.get("final_response")
    require(isinstance(final, dict), "final response evidence missing")
    require(final.get("url") == source_url, "final response URL mismatch")
    status = final.get("response_status")
    require(type(status) is int and 200 <= status <= 299,
            "final response status must be 2xx")
    final_headers = _decode_header_block(
        final.get("response_headers_b64"), final.get("response_headers_sha256"),
        label="final response",
    )
    require(not any(name == "location" for name, _ in final_headers),
            "final response contains an untracked Location header")


def verify(envelope, *, expected_commit, expected_path, market_scope, key_registry,
           now=None, max_age_seconds=86400):
    require(isinstance(envelope, dict), "envelope must be an object")
    validate_evidence_path(expected_path)
    validate_evidence_path(envelope.get("evidence_path"))
    require(envelope.get("expected_commit") == expected_commit, "expected commit mismatch")
    require(envelope.get("evidence_path") == expected_path, "evidence path mismatch")
    require(envelope.get("market_scope") == market_scope, "market scope mismatch")
    digest = envelope.get("raw_sha256", "")
    require(isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "invalid raw SHA-256")

    url = envelope.get("source_url", "")
    parsed_source = validate_https_url(url, label="source URL")
    redirects = envelope.get("redirect_chain")
    require(isinstance(redirects, list) and redirects, "redirect chain missing")
    require(len(redirects) <= MAX_REDIRECT_CHAIN_URLS, "redirect chain exceeds maximum length")
    parsed_redirects = [validate_https_url(redirect, label="redirect URL") for redirect in redirects]
    require(len(set(redirects)) == len(redirects), "redirect chain contains a loop")
    require(
        all(parsed.hostname.lower() == parsed_source.hostname.lower() for parsed in parsed_redirects),
        "redirect chain host continuity violation",
    )
    require(redirects[-1] == url, "redirect chain final URL differs from source URL")
    validate_redirect_hop_evidence(envelope, url, redirects)

    stamp = envelope.get("retrieved_at", "")
    try:
        retrieved = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        require(retrieved.tzinfo is not None and retrieved.utcoffset() is not None, "retrieved_at must include timezone")
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
        require(len(sig) == 64, "invalid Ed25519 signature length")
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
