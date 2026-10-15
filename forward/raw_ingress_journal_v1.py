"""Append-only raw ingress and rejection journal.

This journal is an audit sidecar. It never normalizes or rewrites source bytes,
never deduplicates messages, and never treats a sequence value as authoritative.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class RawIngressJournalError(RuntimeError):
    """The journal is malformed or cannot safely accept another record."""


class RawIngressJournalV1:
    SCHEMA = "hes_raw_ingress_event_v1"
    VERDICTS = {"ACCEPTED", "REJECTED", "IGNORED", "DISCONNECTED", "CONNECTION_ERROR"}

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    @staticmethod
    def _canonical(value: dict[str, Any]) -> bytes:
        try:
            return json.dumps(
                value, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise RawIngressJournalError("EVENT_NOT_JSON_SAFE") from exc

    @staticmethod
    def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RawIngressJournalError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    @classmethod
    def _verify(cls, raw: bytes) -> tuple[int, str | None]:
        if not raw:
            return 0, None
        if not raw.endswith(b"\n"):
            raise RawIngressJournalError("PARTIAL_TRAILING_RECORD")
        previous: str | None = None
        count = 0
        for line_no, line in enumerate(raw.splitlines(), 1):
            try:
                item = json.loads(line.decode("utf-8"), object_pairs_hook=cls._unique_object)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RawIngressJournalError(f"INVALID_JSON_LINE_{line_no}") from exc
            if not isinstance(item, dict):
                raise RawIngressJournalError(f"INVALID_RECORD_LINE_{line_no}")
            digest = item.get("event_sha256")
            body = {k: v for k, v in item.items() if k != "event_sha256"}
            actual = hashlib.sha256(cls._canonical(body)).hexdigest()
            if not isinstance(digest, str) or digest != actual:
                raise RawIngressJournalError(f"EVENT_HASH_MISMATCH_LINE_{line_no}")
            if body.get("schema") != cls.SCHEMA:
                raise RawIngressJournalError(f"SCHEMA_MISMATCH_LINE_{line_no}")
            if body.get("event_no") != line_no:
                raise RawIngressJournalError(f"EVENT_NUMBER_MISMATCH_LINE_{line_no}")
            if body.get("previous_event_sha256") != previous:
                raise RawIngressJournalError(f"HASH_CHAIN_MISMATCH_LINE_{line_no}")
            if body.get("verdict") not in cls.VERDICTS:
                raise RawIngressJournalError(f"VERDICT_INVALID_LINE_{line_no}")
            previous = digest
            count += 1
        return count, previous

    def append(
        self, *, event_type: str, received_at_utc: str,
        receive_monotonic_ns: int, connection_generation: int,
        verdict: str, reason_code: str | None = None,
        raw_bytes: bytes | None = None, details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if verdict not in self.VERDICTS:
            raise RawIngressJournalError("VERDICT_INVALID")
        if not isinstance(event_type, str) or not event_type.strip():
            raise RawIngressJournalError("EVENT_TYPE_REQUIRED")
        if not isinstance(received_at_utc, str) or not received_at_utc.strip():
            raise RawIngressJournalError("UTC_TIMESTAMP_REQUIRED")
        try:
            parsed_timestamp = datetime.fromisoformat(
                received_at_utc[:-1] + "+00:00" if received_at_utc.endswith("Z") else received_at_utc
            )
        except ValueError as exc:
            raise RawIngressJournalError("UTC_TIMESTAMP_INVALID") from exc
        if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() != timedelta(0):
            raise RawIngressJournalError("UTC_TIMESTAMP_MUST_BE_UTC")
        if type(receive_monotonic_ns) is not int or receive_monotonic_ns < 0:
            raise RawIngressJournalError("MONOTONIC_TIMESTAMP_INVALID")
        if type(connection_generation) is not int or connection_generation < 0:
            raise RawIngressJournalError("CONNECTION_GENERATION_INVALID")
        if reason_code is not None and (not isinstance(reason_code, str) or not reason_code.strip()):
            raise RawIngressJournalError("REASON_CODE_INVALID")
        raw = raw_bytes if raw_bytes is not None else b""
        if not isinstance(raw, bytes):
            raise RawIngressJournalError("RAW_BYTES_REQUIRED")
        if details is not None and not isinstance(details, dict):
            raise RawIngressJournalError("DETAILS_INVALID")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_RDWR | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        lock_flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            lock_flags |= os.O_NOFOLLOW
        lock_fd = os.open(self.lock_path, lock_flags, 0o600)
        with os.fdopen(lock_fd, "a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            fd = os.open(self.path, flags, 0o600)
            try:
                existing = b""
                with os.fdopen(os.dup(fd), "rb") as stream:
                    existing = stream.read()
                count, previous = self._verify(existing)
                body: dict[str, Any] = {
                    "schema": self.SCHEMA,
                    "event_no": count + 1,
                    "event_type": event_type,
                    "received_at_utc": received_at_utc,
                    "receive_monotonic_ns": receive_monotonic_ns,
                    "connection_generation": connection_generation,
                    "verdict": verdict,
                    "reason_code": reason_code,
                    "raw_bytes_b64": base64.b64encode(raw).decode("ascii") if raw_bytes is not None else None,
                    "raw_sha256": hashlib.sha256(raw).hexdigest() if raw_bytes is not None else None,
                    "previous_event_sha256": previous,
                    "details": details or {},
                }
                digest = hashlib.sha256(self._canonical(body)).hexdigest()
                encoded = self._canonical({**body, "event_sha256": digest}) + b"\n"
                view = memoryview(encoded)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short journal write")
                    view = view[written:]
                os.fsync(fd)
                return {**body, "event_sha256": digest}
            finally:
                os.close(fd)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
