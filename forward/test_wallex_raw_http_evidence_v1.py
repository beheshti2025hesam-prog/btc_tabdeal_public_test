from datetime import datetime, timezone
import hashlib
import json

import pytest

from forward.wallex_raw_http_evidence_v1 import (
    RawResponseEvidenceError,
    persist_raw_http_response_v1,
    verify_raw_http_response_v1,
)

UTC = timezone.utc
CAPTURED = datetime(2026, 10, 17, 13, 45, tzinfo=UTC)
URL = "https://api.wallex.ir/v1/udf/history?symbol=BTCUSDT&resolution=1"
PARAMS = {"symbol": "BTCUSDT", "resolution": "1", "from": 1792240000, "to": 1792243600}
RAW = b'{ "s" : "ok", "t" : [], "o" : [], "h" : [], "l" : [], "c" : [], "v" : [] }\n'


def persist(path, raw=RAW):
    return persist_raw_http_response_v1(
        path,
        request_url=URL,
        request_params=PARAMS,
        http_status=200,
        received_at=CAPTURED,
        raw_body=raw,
    )


def test_raw_response_bytes_round_trip_exactly(tmp_path):
    path = tmp_path / "raw-response.json"
    meta = persist(path)
    verified = verify_raw_http_response_v1(path)
    assert verified["raw_body"] == RAW
    assert verified["raw_body_sha256"] == hashlib.sha256(RAW).hexdigest()
    assert meta["raw_body_sha256"] == verified["raw_body_sha256"]
    assert verified["request_params"] == PARAMS
    assert verified["http_status"] == 200


def test_existing_evidence_path_is_never_overwritten(tmp_path):
    path = tmp_path / "raw-response.json"
    persist(path)
    original = path.read_bytes()
    with pytest.raises(RawResponseEvidenceError, match="refusing overwrite"):
        persist(path, b"different response")
    assert path.read_bytes() == original


def test_body_tampering_is_detected(tmp_path):
    path = tmp_path / "raw-response.json"
    persist(path)
    envelope = json.loads(path.read_text())
    envelope["raw_body_base64"] = "ZGlmZmVyZW50"
    path.write_text(json.dumps(envelope))
    with pytest.raises(RawResponseEvidenceError, match="SHA-256 mismatch"):
        verify_raw_http_response_v1(path)


def test_invalid_base64_is_rejected(tmp_path):
    path = tmp_path / "raw-response.json"
    persist(path)
    envelope = json.loads(path.read_text())
    envelope["raw_body_base64"] = "not base64!"
    path.write_text(json.dumps(envelope))
    with pytest.raises(RawResponseEvidenceError, match="base64 is invalid"):
        verify_raw_http_response_v1(path)


def test_non_wallex_url_is_rejected(tmp_path):
    with pytest.raises(RawResponseEvidenceError, match="outside the approved"):
        persist_raw_http_response_v1(
            tmp_path / "bad.json",
            request_url="https://example.com/response",
            request_params=PARAMS,
            http_status=200,
            received_at=CAPTURED,
            raw_body=RAW,
        )


def test_naive_capture_timestamp_is_rejected(tmp_path):
    with pytest.raises(RawResponseEvidenceError, match="timezone-aware"):
        persist_raw_http_response_v1(
            tmp_path / "bad.json",
            request_url=URL,
            request_params=PARAMS,
            http_status=200,
            received_at=datetime(2026, 10, 17, 13, 45),
            raw_body=RAW,
        )


def test_recorded_byte_count_tampering_is_rejected(tmp_path):
    path = tmp_path / "raw-response.json"
    persist(path)
    envelope = json.loads(path.read_text())
    envelope["raw_body_bytes"] += 1
    path.write_text(json.dumps(envelope))
    with pytest.raises(RawResponseEvidenceError, match="byte count mismatch"):
        verify_raw_http_response_v1(path)


def test_request_metadata_tampering_is_detected(tmp_path):
    path = tmp_path / "raw-response.json"
    persist(path)
    envelope = json.loads(path.read_text())
    envelope["request_params"]["resolution"] = "15"
    path.write_text(json.dumps(envelope))
    with pytest.raises(RawResponseEvidenceError, match="envelope SHA-256 mismatch"):
        verify_raw_http_response_v1(path)
