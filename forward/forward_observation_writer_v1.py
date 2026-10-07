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


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def observation_digest(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


class ForwardObservationWriterV1:
    def __init__(self, path: str | Path):
        self.path = Path(path)

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
        if payload.get("event_id") != context.forward_run_id + ":" + payload["event_id"]:
            raise ValueError("event_id must be scoped to forward_run_id")

        payload["artifact_type"] = "FORWARD_OBSERVATION"
        payload["artifact_version"] = "1.0"
        payload["digest"] = observation_digest(payload)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            handle.seek(0)
            ids = set()
            for line in handle:
                if line.strip():
                    item = json.loads(line)
                    ids.add(item.get("event_id"))
            if payload["event_id"] in ids:
                raise ValueError("duplicate observation event_id")
            handle.seek(0, 2)
            line = canonical_json(payload) + "\n"
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return payload["digest"]
