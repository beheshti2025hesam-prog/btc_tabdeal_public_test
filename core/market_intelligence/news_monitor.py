"""Durable, continuous news-source monitor built on the canonical NewsIntelligenceBrain.

The monitor is deliberately an observer: it never creates trade direction, changes
risk limits, or enables execution. Snapshots are atomically replaced and carry a
content digest so dashboard readers can detect partial/corrupt writes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from threading import Event, Lock
from typing import Callable

from core.market_intelligence.news_brain import MarketContext, NewsIntelligenceBrain


SCHEMA_VERSION = "hes.news_monitor_snapshot.v1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


class NewsMonitorV1:
    """Periodically refresh one market context using the existing news brain."""

    def __init__(
        self,
        *,
        brain: NewsIntelligenceBrain,
        registry_path: str | Path,
        context: MarketContext,
        snapshot_path: str | Path,
        interval_seconds: int = 60,
        clock: Callable[[], datetime] = _utc_now,
        on_brief: Callable[[object], None] | None = None,
        poll_lock: Lock | None = None,
    ) -> None:
        if type(interval_seconds) is not int or not 15 <= interval_seconds <= 3600:
            raise ValueError("interval_seconds must be an integer from 15 to 3600")
        self.brain = brain
        self.registry_path = Path(registry_path)
        self.context = context
        self.snapshot_path = Path(snapshot_path)
        self.interval_seconds = interval_seconds
        self.clock = clock
        self.on_brief = on_brief
        self.poll_lock = poll_lock or Lock()
        self.last_poll_at: str | None = None
        self.last_success_at: str | None = None
        self.last_status = "NOT_STARTED"
        self.last_error: str | None = None

    def poll_once(self) -> dict:
        # Share the same lock as request-time cache misses to avoid duplicate source fan-out.
        with self.poll_lock:
            started = self.clock()
            if started.tzinfo is None or started.utcoffset() is None:
                raise ValueError("monitor clock must return a timezone-aware datetime")
            started = started.astimezone(timezone.utc)
            self.last_poll_at = started.isoformat(timespec="seconds").replace("+00:00", "Z")
            brief = self.brain.run_from_registry(self.registry_path, self.context, now=started)
            brief_data = brief.to_dict()
            brief_digest = sha256(_canonical(brief_data)).hexdigest()
            degraded = brief.status == "degraded" or bool(brief.provenance.get("source_failures"))
            self.last_status = "DEGRADED" if degraded else "OK"
            self.last_error = None
            if not degraded:
                self.last_success_at = self.last_poll_at
            snapshot = {
                "schema_version": SCHEMA_VERSION,
                "monitor": {
                    "status": self.last_status,
                    "interval_seconds": self.interval_seconds,
                    "last_poll_at": self.last_poll_at,
                    "last_success_at": self.last_success_at,
                    "last_error": None,
                    "source_profile_status": str(brief.provenance.get("source_profile_status", "unknown")),
                    "source_failures": list(brief.provenance.get("source_failures", [])),
                    "source_health": list(brief.provenance.get("source_health", [])),
                },
                "context": {
                    "market": self.context.market,
                    "symbol": self.context.symbol,
                    "venue": self.context.venue,
                    "timeframe": self.context.timeframe,
                },
                "brief": brief_data,
                "brief_sha256": brief_digest,
            }
            self._atomic_write(snapshot)
            if self.on_brief is not None:
                self.on_brief(brief)
            return snapshot

    def record_failure(self, exc: Exception) -> dict:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            now = _utc_now()
        stamp = now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        self.last_poll_at = stamp
        self.last_status = "BLOCKED"
        self.last_error = type(exc).__name__
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "monitor": {
                "status": self.last_status,
                "interval_seconds": self.interval_seconds,
                "last_poll_at": self.last_poll_at,
                "last_success_at": self.last_success_at,
                "last_error": self.last_error,
                "source_profile_status": "unknown",
                "source_failures": [],
                "source_health": [],
            },
            "context": {
                "market": self.context.market,
                "symbol": self.context.symbol,
                "venue": self.context.venue,
                "timeframe": self.context.timeframe,
            },
            "brief": None,
            "brief_sha256": None,
        }
        self._atomic_write(snapshot)
        return snapshot

    def run_forever(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            try:
                self.poll_once()
            except Exception as exc:
                try:
                    self.record_failure(exc)
                except Exception:
                    # The dashboard still fails closed if persistence itself is unavailable.
                    self.last_status = "BLOCKED"
                    self.last_error = "SNAPSHOT_PERSISTENCE_FAILED"
            stop_event.wait(self.interval_seconds)

    def read_snapshot(self, *, max_age_seconds: int | None = None) -> dict:
        raw = self.snapshot_path.read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError("news monitor snapshot exceeds size limit")
        snapshot = json.loads(raw.decode("utf-8"))
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("news monitor snapshot schema mismatch")
        brief = snapshot.get("brief")
        digest = snapshot.get("brief_sha256")
        if brief is not None:
            if not isinstance(brief, dict) or not isinstance(digest, str):
                raise ValueError("news monitor snapshot evidence missing")
            if sha256(_canonical(brief)).hexdigest() != digest:
                raise ValueError("news monitor snapshot digest mismatch")
        monitor = snapshot.get("monitor")
        if not isinstance(monitor, dict) or monitor.get("status") not in {"OK", "DEGRADED", "BLOCKED"}:
            raise ValueError("news monitor status invalid")
        if max_age_seconds is not None:
            stamp = monitor.get("last_poll_at")
            try:
                observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("news monitor timestamp invalid") from exc
            if observed.tzinfo is None:
                raise ValueError("news monitor timestamp timezone missing")
            age_seconds = (_utc_now() - observed.astimezone(timezone.utc)).total_seconds()
            if age_seconds < -30:
                raise ValueError("news monitor timestamp is in the future")
            if age_seconds > max_age_seconds:
                raise ValueError("news monitor snapshot stale")
        return snapshot

    def _atomic_write(self, snapshot: dict) -> None:
        payload = _canonical(snapshot)
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".news-monitor-", suffix=".tmp",
                                         dir=str(self.snapshot_path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.snapshot_path)
            try:
                directory_fd = os.open(self.snapshot_path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
