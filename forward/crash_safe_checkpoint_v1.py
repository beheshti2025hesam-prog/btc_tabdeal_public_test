"""Crash-safe, write-once forward checkpoint metadata.

Checkpoint records are durable descriptive metadata only. They are never
proof of sequence adjacency or permission to resume a continuity segment.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

_SCHEMA = "hes_forward_crash_safe_checkpoint_v1"
_FORBIDDEN_KEYS = {
    "resume_sequence", "last_sequence", "sequence_adjacency",
    "continuity_proof", "sequence_continuity",
}


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("CHECKPOINT_PAYLOAD_NOT_JSON") from exc


def _validate_state(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("CHECKPOINT_STATE_MUST_BE_OBJECT")

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
                if normalized in _FORBIDDEN_KEYS:
                    raise ValueError("CHECKPOINT_CONTINUITY_PROOF_FORBIDDEN")
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    _canonical(value)


@dataclass(frozen=True)
class CheckpointV1:
    checkpoint_id: str
    segment_id: int
    created_at: str
    digest: str
    state: dict[str, Any]


class CrashSafeCheckpointV1:
    """Store immutable checkpoint envelopes using exclusive file creation.

    A duplicate ID always rejects. Partial/corrupt records fail closed and are
    never silently repaired or overwritten. A checkpoint is not continuity proof.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    @staticmethod
    def _timestamp(value: datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("CHECKPOINT_TIMEZONE_REQUIRED")
        return value.astimezone(timezone.utc).isoformat()

    def _path(self, checkpoint_id: str) -> Path:
        if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
            raise ValueError("CHECKPOINT_ID_REQUIRED")
        # Hash IDs so separators or traversal strings cannot escape the root.
        filename = hashlib.sha256(checkpoint_id.encode("utf-8")).hexdigest() + ".json"
        return self.root / filename

    def create(
        self, *, checkpoint_id: str, segment_id: int,
        created_at: datetime, state: dict[str, Any],
    ) -> CheckpointV1:
        if isinstance(segment_id, bool) or not isinstance(segment_id, int) or segment_id < 1:
            raise ValueError("CHECKPOINT_SEGMENT_INVALID")
        stamp = self._timestamp(created_at)
        _validate_state(state)
        payload = {
            "checkpoint_id": checkpoint_id,
            "segment_id": segment_id,
            "created_at": stamp,
            "state": state,
        }
        digest = hashlib.sha256(_canonical(payload)).hexdigest()
        raw = _canonical({"schema": _SCHEMA, "payload": payload, "digest": digest}) + b"\n"
        path = self._path(checkpoint_id)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ValueError("CHECKPOINT_ALREADY_EXISTS") from exc
        # On write/fsync failure, preserve the suspect record for forensic review.
        # Never delete or repair a possibly partial checkpoint automatically.
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        dir_fd = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return CheckpointV1(checkpoint_id, segment_id, stamp, digest, json.loads(_canonical(state)))

    def read(self, checkpoint_id: str) -> CheckpointV1:
        raw = self._path(checkpoint_id).read_bytes()
        try:
            envelope = json.loads(raw.decode("utf-8"))
            if not isinstance(envelope, dict) or envelope.get("schema") != _SCHEMA:
                raise ValueError("CHECKPOINT_SCHEMA_INVALID")
            payload = envelope["payload"]
            digest = envelope["digest"]
            if not isinstance(payload, dict) or not isinstance(digest, str):
                raise ValueError("CHECKPOINT_RECORD_INVALID")
            actual = hashlib.sha256(_canonical(payload)).hexdigest()
            if not hmac.compare_digest(digest, actual):
                raise ValueError("CHECKPOINT_DIGEST_MISMATCH")
            if payload.get("checkpoint_id") != checkpoint_id:
                raise ValueError("CHECKPOINT_ID_MISMATCH")
            segment_id = payload.get("segment_id")
            if isinstance(segment_id, bool) or not isinstance(segment_id, int) or segment_id < 1:
                raise ValueError("CHECKPOINT_SEGMENT_INVALID")
            stamp = payload.get("created_at")
            parsed = datetime.fromisoformat(stamp)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("CHECKPOINT_TIME_INVALID")
            state = payload.get("state")
            _validate_state(state)
            return CheckpointV1(
                checkpoint_id, segment_id,
                parsed.astimezone(timezone.utc).isoformat(), digest,
                json.loads(_canonical(state)),
            )
        except (KeyError, TypeError, AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("CHECKPOINT_RECORD_INVALID") from exc
