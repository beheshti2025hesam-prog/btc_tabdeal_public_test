import hashlib
import json
from pathlib import Path

from scripts.ops.hes_sequence_protocol_drift_audit_v1 import build_report, fetch_source, load_sources


def registry_file(tmp_path, evidence_rows):
    payload = {
        "schema": "hes_sequence_semantics_registry_v1",
        "registry_version": 1,
        "records": [
            {
                "record_id": f"record-{i}",
                "status": "UNKNOWN",
                "capabilities": {"event_identity": False, "ordered_event_sequence": False},
                "source_evidence": evidence,
            }
            for i, evidence in enumerate(evidence_rows)
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def fetch_ok(url, *, timeout, max_bytes):
    body = b"official-doc-content"
    return {"http_status": 200, "final_url": url, "body_bytes": len(body), "content_type": "text/html", "last_modified": "Mon, 16 Nov 2026 00:00:00 GMT", "etag": "test-etag", "actual_sha256": hashlib.sha256(body).hexdigest()}


def test_matching_pinned_source_is_unchanged_and_never_promotes_capabilities(tmp_path):
    body_hash = hashlib.sha256(b"official-doc-content").hexdigest()
    path = registry_file(tmp_path, [{"url": "https://example.org/docs", "source_kind": "primary", "source_content_sha256": body_hash}])
    report = build_report(path, fetcher=fetch_ok)
    assert report["overall_status"] == "OK"
    assert report["sources"][0]["status"] == "SOURCE_UNCHANGED"
    assert report["capabilities_modified"] is False
    assert report["automatic_capability_promotion"] is False


def test_unpinned_source_is_review_required(tmp_path):
    path = registry_file(tmp_path, [{"url": "https://example.org/docs", "source_kind": "primary", "source_content_sha256": None}])
    report = build_report(path, fetcher=fetch_ok)
    assert report["overall_status"] == "REVIEW_REQUIRED"
    assert report["sources"][0]["status"] == "BASELINE_UNPINNED_REVIEW_REQUIRED"


def test_changed_source_is_review_required_not_auto_updated(tmp_path):
    expected = hashlib.sha256(b"old-doc-content").hexdigest()
    path = registry_file(tmp_path, [{"url": "https://example.org/docs", "source_kind": "primary", "source_content_sha256": expected}])
    report = build_report(path, fetcher=fetch_ok)
    assert report["sources"][0]["status"] == "SOURCE_CHANGED_REVIEW_REQUIRED"
    _, registry_hash, _ = load_sources(path)
    assert report["registry_sha256"] == registry_hash


def test_multiple_records_share_one_source_fetch(tmp_path):
    path = registry_file(tmp_path, [
        {"url": "https://example.org/docs", "source_kind": "primary", "source_content_sha256": None},
        {"url": "https://example.org/docs", "source_kind": "primary", "source_content_sha256": None},
    ])
    calls = []
    def counted(url, *, timeout, max_bytes):
        calls.append(url)
        return fetch_ok(url, timeout=timeout, max_bytes=max_bytes)
    report = build_report(path, fetcher=counted)
    assert calls == ["https://example.org/docs"]
    assert report["sources_total"] == 1
    assert report["sources"][0]["record_ids"] == ["record-0", "record-1"]


def test_conflicting_baselines_are_reported_as_registry_error(tmp_path):
    path = registry_file(tmp_path, [
        {"url": "https://example.org/docs", "source_kind": "primary", "source_content_sha256": "a" * 64},
        {"url": "https://example.org/docs", "source_kind": "primary", "source_content_sha256": "b" * 64},
    ])
    report = build_report(path, fetcher=fetch_ok)
    assert report["sources"][0]["status"] == "REGISTRY_BASELINE_CONFLICT_REVIEW_REQUIRED"


def test_fetch_failure_is_review_required_without_crashing_report(tmp_path):
    path = registry_file(tmp_path, [{"url": "https://example.org/docs", "source_kind": "primary", "source_content_sha256": None}])
    def fail(url, *, timeout, max_bytes):
        raise TimeoutError("timeout")
    report = build_report(path, fetcher=fail)
    assert report["sources"][0]["status"] == "SOURCE_FETCH_FAILED_REVIEW_REQUIRED"
    assert report["overall_status"] == "REVIEW_REQUIRED"


def test_fetch_rejects_unapproved_host_without_network_access():
    import pytest
    with pytest.raises(ValueError, match="UNAPPROVED_SOURCE_URL"):
        fetch_source("https://attacker.example/metadata", timeout=1, max_bytes=1000)


def test_audit_preserves_registry_bytes_and_retrieval_metadata(tmp_path):
    path = registry_file(tmp_path, [{"url": "https://example.org/docs", "source_kind": "primary", "source_content_sha256": None}])
    before = path.read_bytes()
    report = build_report(path, fetcher=fetch_ok)
    assert path.read_bytes() == before
    source = report["sources"][0]
    assert source["content_type"] == "text/html"
    assert source["last_modified"] == "Mon, 16 Nov 2026 00:00:00 GMT"
    assert source["etag"] == "test-etag"
    assert report["capabilities_modified"] is False
