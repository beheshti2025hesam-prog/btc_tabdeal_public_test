"""Immutable forward observation artifact writer.

This layer records contemporaneous observations only. It never imports or
mutates historical Winner/Survivor populations and never stores outcomes.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Mapping, Any

from .runtime_guard_v1 import RuntimeContext, validate_context
from .sealed_jsonl_segments_v1 import _locked, _read_records_unlocked, _seal_hot_file_unlocked, read_jsonl_records


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def observation_digest(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


class ForwardObservationWriterV1:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def append(self, record: Mapping[str, Any], *, context: RuntimeContext) -> str:
        validate_context(context)
        payload = dict(record)
        required = ("event_id", "observed_at", "symbol", "timeframe", "status")
        missing = [name for name in required if payload.get(name) in (None, "")]
        if missing:
            raise ValueError("missing observation fields:" + ",".join(missing))
        if payload.get("outcome") is not None or payload.get("closed_at") is not None:
            raise ValueError("future outcome leakage is forbidden")
        if payload.get("source") in {"winner", "survivor", "historical", "legacy"}:
            raise ValueError("historical source is forbidden")
        if payload.get("event_id") != context.forward_run_id + ":" + payload["event_id"].split(":", 1)[-1]:
            raise ValueError("event_id must be scoped to forward_run_id")

        payload["artifact_type"] = "FORWARD_OBSERVATION"
        payload["artifact_version"] = "1.0"
        payload["digest"] = observation_digest(payload)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _locked(self.path, exclusive=True):
            if self.path.is_symlink():
                raise ValueError("observation path must not be a symlink")
            ids = {item.get("event_id") for item in _read_records_unlocked(self.path)}
            if payload["event_id"] in ids:
                raise ValueError("duplicate observation event_id")
            with self.path.open("ab") as handle:
                handle.write((canonical_json(payload) + "\n").encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
        return payload["digest"]


    def read(self) -> list[dict[str, Any]]:
        """Read verified sealed segments followed by the active observation tail."""
        return read_jsonl_records(self.path)

    def seal(self) -> dict[str, Any] | None:
        """Seal the closed observation prefix under the same lock used by append()."""
        with _locked(self.path, exclusive=True):
            return _seal_hot_file_unlocked(self.path)