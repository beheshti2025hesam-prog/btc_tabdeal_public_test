"""Fetch raw HTTPS source bytes and emit a detached Ed25519 attestation.

This is a producer utility, not a trust root. Its signing key MUST be supplied
from an independently governed runtime (never committed to this repository).
The caller is responsible for operating it in that trusted environment.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

TOOL_NAME = "hes-independent-source-attestor"
TOOL_VERSION = "1.0.0"
MAX_RESPONSE_BYTES = 10 * 1024 * 1024


def canonical_payload(attestation: dict) -> bytes:
    payload = {key: value for key, value in attestation.items() if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _validate_url(url: str, allowed_hosts: set[str]) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.hostname.lower() not in allowed_hosts
    ):
        raise ValueError("BLOCK: URL is not HTTPS on an explicitly allowed exact host")


class _RecordingRedirectHandler(HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str]):
        super().__init__()
        self.allowed_hosts = allowed_hosts
        self.chain: list[dict] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl, self.allowed_hosts)
        self.chain.append({
            "url": req.full_url,
            "status": int(code),
            "next_url": newurl,
        })
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def retrieve_and_attest(
    *, url: str, allowed_hosts: set[str], context: dict,
    snapshot_path: str | Path, attestation_path: str | Path,
) -> dict:
    """Retrieve bytes from allow-listed HTTPS URL and sign their provenance."""
    if not allowed_hosts:
        raise ValueError("BLOCK: at least one exact allowed host is required")
    _validate_url(url, allowed_hosts)
    private_b64 = os.environ.get("HES_SOURCE_ATTESTATION_PRIVATE_KEY_B64")
    key_id = os.environ.get("HES_SOURCE_ATTESTATION_KEY_ID")
    if not private_b64 or not key_id or not key_id.strip():
        raise ValueError("BLOCK: independently provisioned signing key and key ID are required")

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_b64, validate=True))
    except Exception as exc:
        raise ValueError("BLOCK: invalid Ed25519 private key configuration") from exc

    redirect_handler = _RecordingRedirectHandler(allowed_hosts)
    opener = build_opener(redirect_handler)
    request = Request(url, headers={"User-Agent": f"{TOOL_NAME}/{TOOL_VERSION}", "Accept-Encoding": "identity"})
    with opener.open(request, timeout=20) as response:
        final_url = response.geturl()
        _validate_url(final_url, allowed_hosts)
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("BLOCK: source response exceeds size limit")
        status = int(response.status)
        if not 200 <= status <= 299:
            raise ValueError("BLOCK: final response is not successful")
        chain = list(redirect_handler.chain)
        chain.append({"url": final_url, "status": status})
    if not raw:
        raise ValueError("BLOCK: empty source response")
    if chain[0]["url"] != url or chain[-1]["url"] != final_url:
        raise ValueError("BLOCK: recorded redirect chain is inconsistent")

    snapshot = Path(snapshot_path)
    attestation_file = Path(attestation_path)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    attestation_file.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    attestation = {
        "schema_version": "hes-source-attestation-v1",
        "snapshot_sha256": digest,
        "requested_url": url,
        "final_url": final_url,
        "redirect_chain": chain,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "retrieval_tool": TOOL_NAME,
        "retrieval_tool_version": TOOL_VERSION,
        "source_context": context,
        "signer_key_id": key_id,
    }
    attestation["signature"] = base64.b64encode(private_key.sign(canonical_payload(attestation))).decode("ascii")
    snapshot.write_bytes(raw)
    attestation_file.write_text(json.dumps(attestation, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"snapshot_sha256": digest, "requested_url": url, "final_url": final_url, "attestation_path": str(attestation_file), "snapshot_path": str(snapshot)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--allow-host", action="append", required=True, help="Exact HTTPS hostname; repeat for each approved host")
    parser.add_argument("--context-json", required=True, help="JSON object binding venue/product/endpoint/channel/field")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--attestation", required=True)
    args = parser.parse_args(argv)
    try:
        context = json.loads(args.context_json)
        if not isinstance(context, dict) or not context:
            raise ValueError("BLOCK: context must be a non-empty JSON object")
        result = retrieve_and_attest(
            url=args.url, allowed_hosts={host.lower() for host in args.allow_host},
            context=context, snapshot_path=args.snapshot, attestation_path=args.attestation,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
