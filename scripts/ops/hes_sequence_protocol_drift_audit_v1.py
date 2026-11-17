#!/usr/bin/env python3
"""Read-only monitor for source-document drift in the HES sequence registry.

This tool never edits registry records or grants protocol capabilities. A changed,
unpinned, conflicting, or unreachable source only creates a review-required result.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlsplit

SCHEMA = "hes_sequence_semantics_registry_v1"
DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "forward" / "sequence_semantics_registry_v1.json"
USER_AGENT = "HES-Sequence-Protocol-Drift-Watch/1.0 (+read-only; evidence-monitor)"
ALLOWED_SOURCE_HOSTS = frozenset({
    "docs.tabdeal.org",
    "github.com",
    "developers.binance.com",
    "www.binance.com",
    "binance.com",
    "www.okx.com",
    "okx.com",
    "bybit-exchange.github.io",
    "docs.cdp.coinbase.com",
    "docs.kraken.com",
    "www.gate.com",
    "gate.com",
})


class SafeHTTPSRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_SOURCE_HOSTS
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            raise ValueError("UNAPPROVED_SOURCE_REDIRECT")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def load_sources(registry_path: Path) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    raw = registry_path.read_bytes()
    registry_hash = sha256(raw)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError("SEQUENCE_REGISTRY_SCHEMA_INVALID")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("SEQUENCE_REGISTRY_RECORDS_INVALID")

    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("SEQUENCE_REGISTRY_RECORD_INVALID")
        evidence = record.get("source_evidence")
        if not isinstance(evidence, dict) or evidence.get("source_kind") != "primary":
            continue
        url = evidence.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            continue
        row = grouped.setdefault(url, {"url": url, "record_ids": [], "expected_hashes": set()})
        row["record_ids"].append(str(record.get("record_id", "UNKNOWN_RECORD")))
        expected = evidence.get("source_content_sha256")
        if expected is not None:
            if not _valid_sha(expected):
                row["expected_hashes"].add("INVALID:" + str(expected))
            else:
                row["expected_hashes"].add(expected.lower())

    sources = []
    for url in sorted(grouped):
        item = grouped[url]
        hashes = item.pop("expected_hashes")
        if len(hashes) > 1:
            item["baseline_state"] = "CONFLICTING_BASELINES"
            item["expected_sha256"] = None
        elif hashes:
            only = next(iter(hashes))
            if only.startswith("INVALID:"):
                item["baseline_state"] = "INVALID_BASELINE"
                item["expected_sha256"] = None
            else:
                item["baseline_state"] = "PINNED"
                item["expected_sha256"] = only
        else:
            item["baseline_state"] = "UNPINNED"
            item["expected_sha256"] = None
        item["record_ids"].sort()
        sources.append(item)
    return payload, registry_hash, sources


def fetch_source(url: str, *, timeout: float, max_bytes: int) -> dict[str, Any]:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_SOURCE_HOSTS
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443)):
        raise ValueError("UNAPPROVED_SOURCE_URL")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain,application/json,*/*"})
    opener = build_opener(SafeHTTPSRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        final_url = response.geturl()
        final = urlsplit(final_url)
        if (final.scheme != "https" or final.hostname not in ALLOWED_SOURCE_HOSTS
                or final.username is not None or final.password is not None
                or final.port not in (None, 443)):
            raise ValueError("UNAPPROVED_SOURCE_REDIRECT")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("SOURCE_BODY_EXCEEDS_MAX_BYTES")
        return {
            "http_status": int(getattr(response, "status", 200)),
            "final_url": final_url,
            "body_bytes": len(body),
            "content_type": response.headers.get("Content-Type"),
            "last_modified": response.headers.get("Last-Modified"),
            "etag": response.headers.get("ETag"),
            "actual_sha256": sha256(body),
        }


def build_report(registry_path: Path, *, timeout: float = 15.0, max_bytes: int = 8_000_000,
                 fetcher=fetch_source) -> dict[str, Any]:
    payload, registry_hash, sources = load_sources(registry_path)
    results: list[dict[str, Any]] = []
    for source in sources:
        result = {key: value for key, value in source.items()}
        try:
            fetched = fetcher(source["url"], timeout=timeout, max_bytes=max_bytes)
            result.update(fetched)
            if source["baseline_state"] == "CONFLICTING_BASELINES":
                result["status"] = "REGISTRY_BASELINE_CONFLICT_REVIEW_REQUIRED"
            elif source["baseline_state"] == "INVALID_BASELINE":
                result["status"] = "REGISTRY_BASELINE_INVALID_REVIEW_REQUIRED"
            elif source["baseline_state"] == "UNPINNED":
                result["status"] = "BASELINE_UNPINNED_REVIEW_REQUIRED"
            elif fetched["actual_sha256"] != source["expected_sha256"]:
                result["status"] = "SOURCE_CHANGED_REVIEW_REQUIRED"
            else:
                result["status"] = "SOURCE_UNCHANGED"
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            result["status"] = "SOURCE_FETCH_FAILED_REVIEW_REQUIRED"
            result["error_type"] = type(exc).__name__
            result["error"] = str(exc)[:240]
        results.append(result)

    review_count = sum(row["status"] != "SOURCE_UNCHANGED" for row in results)
    return {
        "schema": "hes_sequence_protocol_drift_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "registry_path": str(registry_path),
        "registry_sha256": registry_hash,
        "registry_version": payload.get("registry_version"),
        "records_total": len(payload.get("records", [])),
        "sources_total": len(results),
        "review_required_sources": review_count,
        "overall_status": "REVIEW_REQUIRED" if review_count else "OK",
        "capabilities_modified": False,
        "automatic_capability_promotion": False,
        "policy": "DOCUMENT_DRIFT_ONLY; HUMAN_REVIEW_REQUIRED; UNKNOWN_NEVER_GRANTS_CAPABILITY",
        "sources": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--max-bytes", type=int, default=8_000_000)
    parser.add_argument("--strict", action="store_true", help="return exit code 2 when any review is required")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.max_bytes <= 0:
        parser.error("--timeout and --max-bytes must be positive")
    report = build_report(args.registry, timeout=args.timeout, max_bytes=args.max_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SEQUENCE_PROTOCOL_AUDIT={report['overall_status']} sources={report['sources_total']} review_required={report['review_required_sources']} registry_sha256={report['registry_sha256']}")
    return 2 if args.strict and report["overall_status"] != "OK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
