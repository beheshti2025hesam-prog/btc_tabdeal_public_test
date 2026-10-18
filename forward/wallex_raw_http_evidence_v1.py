"""Immutable evidence envelope for exact raw Wallex HTTP response bytes."""
from __future__ import annotations

import base64
import binascii
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


class RawResponseEvidenceError(ValueError):
    """Raw HTTP evidence is missing, overwritten, or fails integrity checks."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def persist_raw_http_response_v1(
    path: str | Path,
    *,
    request_url: str,
    request_params: dict[str, Any],
    http_status: int,
    received_at: datetime,
    raw_body: bytes,
) -> dict[str, Any]:
    """Persist exact response bytes once; never overwrite an existing evidence path."""
    target = Path(path)
    if not isinstance(raw_body, bytes):
        raise RawResponseEvidenceError("raw_body must be bytes")
    if not isinstance(http_status, int) or isinstance(http_status, bool) or not 100 <= http_status <= 599:
        raise RawResponseEvidenceError("invalid HTTP status")
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise RawResponseEvidenceError("received_at must be timezone-aware")
    if not isinstance(request_url, str) or not request_url.startswith("https://api.wallex.ir/"):
        raise RawResponseEvidenceError("request URL is outside the approved public Wallex API")
    if not isinstance(request_params, dict):
        raise RawResponseEvidenceError("request_params must be an object")

    raw_hash = hashlib.sha256(raw_body).hexdigest()
    envelope = {
        "schema": "HES_WALLEX_RAW_HTTP_RESPONSE_V1",
        "request_url": request_url,
        "request_params": request_params,
        "http_status": http_status,
        "received_at": received_at.isoformat(),
        "raw_body_encoding": "base64",
        "raw_body_base64": base64.b64encode(raw_body).decode("ascii"),
        "raw_body_bytes": len(raw_body),
        "raw_body_sha256": raw_hash,
    }
    envelope["evidence_envelope_sha256"] = hashlib.sha256(_canonical(envelope)).hexdigest()
    serialized = _canonical(envelope) + b"\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise RawResponseEvidenceError("evidence path already exists; refusing overwrite") from None
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            dir_fd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            # File content is already fsynced; some platforms do not support
            # directory fsync. Do not claim stronger durability than available.
            pass
    except Exception:
        try:
            target.unlink(missing_ok=True)
        finally:
            raise
    return {
        "schema": envelope["schema"],
        "evidence_path": str(target),
        "raw_body_bytes": len(raw_body),
        "raw_body_sha256": raw_hash,
        "http_status": http_status,
        "received_at": received_at.isoformat(),
    }


def verify_raw_http_response_v1(path: str | Path) -> dict[str, Any]:
    """Verify the envelope and return metadata plus the exact recovered body bytes."""
    try:
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise RawResponseEvidenceError("evidence envelope is unreadable or invalid JSON") from None
    if not isinstance(envelope, dict) or envelope.get("schema") != "HES_WALLEX_RAW_HTTP_RESPONSE_V1":
        raise RawResponseEvidenceError("unsupported raw-response evidence schema")
    claimed_envelope_hash = envelope.get("evidence_envelope_sha256")
    envelope_body = {key: value for key, value in envelope.items() if key != "evidence_envelope_sha256"}
    actual_envelope_hash = hashlib.sha256(_canonical(envelope_body)).hexdigest()
    if not isinstance(claimed_envelope_hash, str) or claimed_envelope_hash != actual_envelope_hash:
        raise RawResponseEvidenceError("evidence envelope SHA-256 mismatch")
    request_url = envelope.get("request_url")
    request_params = envelope.get("request_params")
    if not isinstance(request_url, str) or not isinstance(request_params, dict):
        raise RawResponseEvidenceError("request provenance metadata is missing")
    parsed_url = urlsplit(request_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "api.wallex.ir" or parsed_url.path != "/v1/udf/history":
        raise RawResponseEvidenceError("request URL is outside the approved public Wallex endpoint")
    try:
        query = parse_qs(parsed_url.query, strict_parsing=True)
    except ValueError:
        raise RawResponseEvidenceError("request URL query is invalid") from None
    expected_query = {key: [str(value)] for key, value in request_params.items()}
    if query != expected_query:
        raise RawResponseEvidenceError("request URL and parameter metadata disagree")
    if envelope.get("http_status") != 200:
        raise RawResponseEvidenceError("only HTTP 200 response evidence is accepted")
    received_at = envelope.get("received_at")
    try:
        parsed_received_at = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise RawResponseEvidenceError("received_at timestamp is invalid") from None
    if parsed_received_at.tzinfo is None or parsed_received_at.utcoffset() is None:
        raise RawResponseEvidenceError("received_at timestamp must be timezone-aware")
    if envelope.get("raw_body_encoding") != "base64":
        raise RawResponseEvidenceError("unsupported raw body encoding")
    encoded = envelope.get("raw_body_base64")
    if not isinstance(encoded, str):
        raise RawResponseEvidenceError("raw body bytes are missing")
    try:
        raw_body = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise RawResponseEvidenceError("raw body base64 is invalid") from None
    if type(envelope.get("raw_body_bytes")) is not int or len(raw_body) != envelope["raw_body_bytes"]:
        raise RawResponseEvidenceError("raw body byte count mismatch")
    actual = hashlib.sha256(raw_body).hexdigest()
    if envelope.get("raw_body_sha256") != actual:
        raise RawResponseEvidenceError("raw body SHA-256 mismatch")
    return {
        "schema": envelope["schema"],
        "request_url": envelope.get("request_url"),
        "request_params": envelope.get("request_params"),
        "http_status": envelope.get("http_status"),
        "received_at": envelope.get("received_at"),
        "raw_body_bytes": len(raw_body),
        "raw_body_sha256": actual,
        "evidence_envelope_sha256": actual_envelope_hash,
        "raw_body": raw_body,
    }
