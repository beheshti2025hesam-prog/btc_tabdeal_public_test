"""Fail-closed append-only session supervisor ledger.

Operational ledger primitive only: no sockets, collection, decisions, or orders.
Restarts, interruptions, unhealthy heartbeats, journal damage, and writer
contention invalidate continuity. This module does not start a service.
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCHEMA = "hes_forward_observation_supervisor_event_v1"
INTERRUPTION_TYPES = {"INTERRUPTION", "SESSION_INTERRUPTED"}


class SupervisorError(RuntimeError):
    """A fail-closed supervisor ledger error."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SupervisorError("JOURNAL_PAYLOAD_INVALID") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SupervisorError("JOURNAL_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _parse_line(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SupervisorError("JOURNAL_RECORD_INVALID") from exc
    if not isinstance(value, dict):
        raise SupervisorError("JOURNAL_RECORD_INVALID")
    digest = value.get("event_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise SupervisorError("JOURNAL_DIGEST_MISSING")
    body = {key: item for key, item in value.items() if key != "event_sha256"}
    actual = hashlib.sha256(_canonical(body)).hexdigest()
    if not hmac.compare_digest(actual, digest):
        raise SupervisorError("JOURNAL_DIGEST_MISMATCH")
    return value


class ForwardObservationSupervisorV1:
    """Append-only ledger with an exclusive process-held writer lock.

    Production callers must supply the operating-system boot identity. Use a
    fresh run_id for every process/session attempt; never auto-resume a run.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        run_id: str,
        boot_id: str,
        utc_now: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise SupervisorError("RUN_ID_REQUIRED")
        if not isinstance(boot_id, str) or not boot_id.strip():
            raise SupervisorError("BOOT_ID_REQUIRED")
        self.root = Path(root)
        self.run_id = run_id
        self.boot_id = boot_id
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self.journal_path = self.root / "supervisor_events.jsonl"
        self.lock_path = self.root / "supervisor_writer.lock"
        self._lock_fd: int | None = None
        self._started = False
        self._interrupted = False

    @staticmethod
    def _timestamp(value: datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:
            raise SupervisorError("UTC_CLOCK_MUST_BE_TIMEZONE_AWARE")
        return value.astimezone(timezone.utc).isoformat()

    def _acquire(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink():
            raise SupervisorError("STORAGE_ROOT_SYMLINK_FORBIDDEN")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.lock_path, flags, 0o600)
        except OSError as exc:
            raise SupervisorError("WRITER_LOCK_OPEN_FAILED") from exc
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise SupervisorError("WRITER_ALREADY_HELD") from exc
        self._lock_fd = fd

    def _read_verified(self) -> list[dict[str, Any]]:
        if self.journal_path.is_symlink():
            raise SupervisorError("JOURNAL_SYMLINK_FORBIDDEN")
        if not self.journal_path.exists():
            return []
        events: list[dict[str, Any]] = []
        previous_digest: str | None = None
        active_run: str | None = None
        interrupted_runs: set[str] = set()
        seen_runs: set[str] = set()
        last_mono_by_run: dict[tuple[str, str], int] = {}
        try:
            with self.journal_path.open("r", encoding="utf-8", newline="") as stream:
                for expected_no, line in enumerate(stream, start=1):
                    if not line.endswith("\n") or not line.strip():
                        raise SupervisorError("JOURNAL_PARTIAL_OR_BLANK_LINE")
                    event = _parse_line(line)
                    if event.get("schema") != SCHEMA:
                        raise SupervisorError("JOURNAL_SCHEMA_INVALID")
                    event_no = event.get("event_no")
                    if isinstance(event_no, bool) or not isinstance(event_no, int) or event_no != expected_no:
                        raise SupervisorError("JOURNAL_SEQUENCE_INVALID")
                    required_fields = {
                        "schema", "event_no", "event_type", "run_id", "at_utc",
                        "monotonic_ns", "boot_id", "previous_event_sha256", "details",
                        "event_sha256",
                    }
                    if set(event) != required_fields:
                        raise SupervisorError("JOURNAL_EVENT_SCHEMA_INVALID")
                    event_type = event.get("event_type")
                    if event_type not in {"SESSION_STARTED", "HEARTBEAT", "INTERRUPTION", "SESSION_INTERRUPTED", "SESSION_STOPPED"}:
                        raise SupervisorError("JOURNAL_EVENT_SCHEMA_INVALID")
                    run_id = event.get("run_id")
                    boot_id = event.get("boot_id")
                    mono = event.get("monotonic_ns")
                    details = event.get("details")
                    at_utc = event.get("at_utc")
                    if not isinstance(run_id, str) or not run_id.strip():
                        raise SupervisorError("JOURNAL_EVENT_SCHEMA_INVALID")
                    if not isinstance(boot_id, str) or not boot_id.strip():
                        raise SupervisorError("JOURNAL_EVENT_SCHEMA_INVALID")
                    if isinstance(mono, bool) or not isinstance(mono, int) or mono < 0:
                        raise SupervisorError("JOURNAL_EVENT_SCHEMA_INVALID")
                    if not isinstance(details, dict):
                        raise SupervisorError("JOURNAL_EVENT_SCHEMA_INVALID")
                    if event_type == "HEARTBEAT":
                        source_health = details.get("source_health")
                        reason_code = details.get("reason_code")
                        if source_health != "HEALTHY":
                            raise SupervisorError("JOURNAL_HEARTBEAT_SOURCE_HEALTH_INVALID")
                        if not isinstance(reason_code, str) or not reason_code.strip() or len(reason_code) > 120:
                            raise SupervisorError("JOURNAL_HEARTBEAT_REASON_INVALID")
                    if not isinstance(at_utc, str):
                        raise SupervisorError("JOURNAL_EVENT_SCHEMA_INVALID")
                    try:
                        parsed_utc = datetime.fromisoformat(at_utc.replace("Z", "+00:00"))
                    except ValueError as exc:
                        raise SupervisorError("JOURNAL_EVENT_SCHEMA_INVALID") from exc
                    if parsed_utc.tzinfo is None or parsed_utc.utcoffset() is None:
                        raise SupervisorError("JOURNAL_EVENT_SCHEMA_INVALID")
                    if event.get("previous_event_sha256") != previous_digest:
                        raise SupervisorError("JOURNAL_CHAIN_BROKEN")

                    # A valid digest chain is not sufficient: enforce lifecycle,
                    # run ownership, boot identity, and per-run monotonic order.
                    monotonic_key = (run_id, boot_id)
                    if monotonic_key in last_mono_by_run and mono < last_mono_by_run[monotonic_key]:
                        raise SupervisorError("JOURNAL_MONOTONIC_REGRESSION")

                    if event_type == "SESSION_STARTED":
                        if active_run is not None or run_id in seen_runs:
                            raise SupervisorError("JOURNAL_LIFECYCLE_INVALID")
                        active_run = run_id
                        seen_runs.add(run_id)
                        interrupted_runs.discard(run_id)
                    elif event_type in {"HEARTBEAT", "INTERRUPTION", "SESSION_INTERRUPTED", "SESSION_STOPPED"}:
                        if active_run != run_id:
                            raise SupervisorError("JOURNAL_EVENT_RUN_MISMATCH")
                        if event_type == "HEARTBEAT":
                            if run_id in interrupted_runs:
                                raise SupervisorError("JOURNAL_LIFECYCLE_INVALID")
                        elif event_type in INTERRUPTION_TYPES:
                            if run_id in interrupted_runs:
                                raise SupervisorError("JOURNAL_LIFECYCLE_INVALID")
                            interrupted_runs.add(run_id)
                        elif event_type == "SESSION_STOPPED":
                            stopped_interrupted = details.get("interrupted")
                            if type(stopped_interrupted) is not bool or (run_id in interrupted_runs and not stopped_interrupted):
                                raise SupervisorError("JOURNAL_LIFECYCLE_INVALID")
                            # A failed durable interruption write may still leave
                            # the in-memory session invalidated; the stop marker
                            # must preserve that conservative state.
                            if stopped_interrupted:
                                interrupted_runs.add(run_id)
                            active_run = None
                    last_mono_by_run[monotonic_key] = mono
                    previous_digest = event["event_sha256"]
                    events.append(event)
        except UnicodeError as exc:
            raise SupervisorError("JOURNAL_ENCODING_INVALID") from exc
        return events

    def _append(
        self,
        events: list[dict[str, Any]],
        *,
        event_type: str,
        run_id: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        mono = self._monotonic_ns()
        if isinstance(mono, bool) or not isinstance(mono, int) or mono < 0:
            raise SupervisorError("MONOTONIC_CLOCK_INVALID")
        body = {
            "schema": SCHEMA,
            "event_no": len(events) + 1,
            "event_type": event_type,
            "run_id": run_id,
            "at_utc": self._timestamp(self._utc_now()),
            "monotonic_ns": mono,
            "boot_id": self.boot_id,
            "previous_event_sha256": events[-1]["event_sha256"] if events else None,
            "details": details or {},
        }
        envelope = dict(body)
        envelope["event_sha256"] = hashlib.sha256(_canonical(body)).hexdigest()
        raw = _canonical(envelope) + b"\n"
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.journal_path, flags, 0o600)
            with os.fdopen(fd, "ab") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            dir_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError as exc:
            raise SupervisorError("JOURNAL_DURABLE_WRITE_FAILED") from exc
        events.append(envelope)
        return envelope

    @staticmethod
    def _active_run(events: list[dict[str, Any]]) -> str | None:
        active: str | None = None
        for event in events:
            if event["event_type"] == "SESSION_STARTED":
                active = event["run_id"]
            elif event["event_type"] == "SESSION_STOPPED" and active == event["run_id"]:
                active = None
        return active

    def start(self) -> dict[str, Any]:
        if self._started:
            raise SupervisorError("SESSION_ALREADY_STARTED")
        self._acquire()
        try:
            events = self._read_verified()
            if any(e["run_id"] == self.run_id and e["event_type"] == "SESSION_STARTED" for e in events):
                raise SupervisorError("RUN_ID_REUSE_FORBIDDEN")
            prior = self._active_run(events)
            if prior is not None:
                already_interrupted = any(
                    e["run_id"] == prior and e["event_type"] in INTERRUPTION_TYPES
                    for e in events
                )
                if not already_interrupted:
                    self._append(events, event_type="INTERRUPTION", run_id=prior,
                                 details={"reason_code": "PRIOR_SESSION_UNCLOSED"})
                self._append(events, event_type="SESSION_STOPPED", run_id=prior,
                             details={"reason_code": "PROCESS_RESTART_DETECTED", "interrupted": True})
            event = self._append(
                events, event_type="SESSION_STARTED", run_id=self.run_id,
                details={"mode": "OBSERVATION_ONLY", "decision": "NO_TRADE_ONLY", "execution_enabled": False},
            )
            self._started = True
            return event
        except Exception:
            self.close()
            raise

    def heartbeat(self, *, healthy: bool, reason_code: str = "HEALTHY") -> dict[str, Any]:
        if not self._started:
            raise SupervisorError("SESSION_NOT_STARTED")
        if self._interrupted:
            raise SupervisorError("SESSION_ALREADY_INTERRUPTED")
        if type(healthy) is not bool:
            raise SupervisorError("HEALTH_FLAG_INVALID")
        if not isinstance(reason_code, str) or not reason_code.strip() or len(reason_code) > 120:
            raise SupervisorError("REASON_CODE_INVALID")
        events = self._read_verified()
        if self._active_run(events) != self.run_id:
            raise SupervisorError("SESSION_OWNERSHIP_LOST")
        if not healthy:
            self._interrupted = True
            return self._append(events, event_type="INTERRUPTION", run_id=self.run_id,
                                details={"reason_code": reason_code})
        return self._append(events, event_type="HEARTBEAT", run_id=self.run_id,
                            details={"source_health": "HEALTHY", "reason_code": reason_code})

    def interrupt(self, reason_code: str) -> dict[str, Any]:
        if not self._started:
            raise SupervisorError("SESSION_NOT_STARTED")
        if self._interrupted:
            raise SupervisorError("SESSION_ALREADY_INTERRUPTED")
        if not isinstance(reason_code, str) or not reason_code.strip() or len(reason_code) > 120:
            raise SupervisorError("REASON_CODE_INVALID")
        events = self._read_verified()
        if self._active_run(events) != self.run_id:
            raise SupervisorError("SESSION_OWNERSHIP_LOST")
        self._interrupted = True
        return self._append(events, event_type="INTERRUPTION", run_id=self.run_id,
                            details={"reason_code": reason_code})

    def stop(self, reason_code: str = "OPERATOR_STOP") -> dict[str, Any]:
        if not self._started:
            raise SupervisorError("SESSION_NOT_STARTED")
        if not isinstance(reason_code, str) or not reason_code.strip() or len(reason_code) > 120:
            raise SupervisorError("REASON_CODE_INVALID")
        events = self._read_verified()
        if self._active_run(events) != self.run_id:
            raise SupervisorError("SESSION_OWNERSHIP_LOST")
        event = self._append(events, event_type="SESSION_STOPPED", run_id=self.run_id,
                             details={"reason_code": reason_code, "interrupted": self._interrupted})
        self._started = False
        self.close()
        return event

    def continuity_report(
        self, *, required_seconds: float = 48 * 60 * 60,
        max_heartbeat_gap_seconds: float = 90.0,
    ) -> dict[str, Any]:
        limits = (required_seconds, max_heartbeat_gap_seconds)
        try:
            valid_limits = all(
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(float(value))
                and value > 0
                for value in limits
            )
        except (OverflowError, TypeError, ValueError):
            valid_limits = False
        if not valid_limits:
            raise SupervisorError("CONTINUITY_LIMIT_INVALID")
        events = self._read_verified()
        selected = [e for e in events if e["run_id"] == self.run_id]
        starts = [e for e in selected if e["event_type"] == "SESSION_STARTED"]
        heartbeats = [e for e in selected if e["event_type"] == "HEARTBEAT"]
        interruptions = [e for e in selected if e["event_type"] in INTERRUPTION_TYPES]
        if len(starts) != 1:
            return {"run_id": self.run_id, "proven": False, "reason": "START_RECORD_MISSING_OR_DUPLICATE", "continuous_seconds": 0.0}
        start = starts[0]
        stops = [e for e in selected if e["event_type"] == "SESSION_STOPPED"]
        if len(stops) != 1:
            return {"run_id": self.run_id, "proven": False, "reason": "SESSION_NOT_STOPPED_OR_DUPLICATE_STOP", "continuous_seconds": 0.0}
        stop_details = stops[0].get("details")
        end_mono = stops[0]["monotonic_ns"]
        start_mono = start["monotonic_ns"]
        if (
            isinstance(end_mono, bool)
            or not isinstance(end_mono, int)
            or end_mono < 0
            or isinstance(start_mono, bool)
            or not isinstance(start_mono, int)
            or start_mono < 0
        ):
            raise SupervisorError("MONOTONIC_CLOCK_INVALID")
        if end_mono < start_mono:
            return {"run_id": self.run_id, "proven": False, "reason": "MONOTONIC_CLOCK_REGRESSION", "continuous_seconds": 0.0}
        elapsed = (end_mono - start_mono) / 1_000_000_000
        if interruptions or not isinstance(stop_details, dict) or stop_details.get("interrupted") is not False:
            return {"run_id": self.run_id, "proven": False, "reason": "INTERRUPTION_RECORDED", "continuous_seconds": elapsed}
        if any(e["boot_id"] != start["boot_id"] for e in selected):
            return {"run_id": self.run_id, "proven": False, "reason": "BOOT_ID_CHANGED", "continuous_seconds": elapsed}
        if not heartbeats:
            return {"run_id": self.run_id, "proven": False, "reason": "HEARTBEAT_MISSING", "continuous_seconds": elapsed}
        points = [start_mono] + [e["monotonic_ns"] for e in heartbeats] + [end_mono]
        if any(right < left for left, right in zip(points, points[1:])):
            return {"run_id": self.run_id, "proven": False, "reason": "MONOTONIC_CLOCK_REGRESSION", "continuous_seconds": elapsed}
        max_gap_ns = int(max_heartbeat_gap_seconds * 1_000_000_000)
        if any(right - left > max_gap_ns for left, right in zip(points, points[1:])):
            return {"run_id": self.run_id, "proven": False, "reason": "HEARTBEAT_GAP_EXCEEDED", "continuous_seconds": elapsed}
        if elapsed < required_seconds:
            return {"run_id": self.run_id, "proven": False, "reason": "REQUIRED_DURATION_NOT_MET", "continuous_seconds": elapsed}
        return {"run_id": self.run_id, "proven": True, "reason": "CONTINUITY_PROVEN", "continuous_seconds": elapsed}

    def close(self) -> None:
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(self._lock_fd)
                self._lock_fd = None

    def __enter__(self) -> "ForwardObservationSupervisorV1":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._started:
            if exc is not None and not self._interrupted:
                try:
                    self.interrupt("UNHANDLED_PROCESS_EXCEPTION")
                except SupervisorError:
                    pass
            if self._started:
                try:
                    self.stop("CONTEXT_EXIT")
                except SupervisorError:
                    self.close()
        else:
            self.close()
