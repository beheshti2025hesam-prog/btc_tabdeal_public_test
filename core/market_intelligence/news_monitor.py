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
import fcntl
from pathlib import Path
import tempfile
import time
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
        interval_seconds: int = 300,
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
            # Keep transport health separate from publication freshness. A low-frequency
            # official feed may be reachable while its newest item is old; an empty feed
            # is not evidence of freshness or failure.
            source_health = []
            for source in brief.provenance.get("source_health", []):
                row = dict(source)
                newest = row.get("newest_published_at")
                if row.get("status") == "failed":
                    row["freshness_status"] = "failed"
                    row["newest_age_minutes"] = None
                elif row.get("status") == "ok_empty":
                    row["freshness_status"] = "empty"
                    row["newest_age_minutes"] = None
                elif not newest:
                    row["freshness_status"] = "unknown"
                    row["newest_age_minutes"] = None
                else:
                    try:
                        published = datetime.fromisoformat(str(newest).replace("Z", "+00:00"))
                        if published.tzinfo is None or published.utcoffset() is None:
                            raise ValueError("timezone missing")
                        age_minutes = (started - published.astimezone(timezone.utc)).total_seconds() / 60
                        row["newest_age_minutes"] = round(age_minutes, 1)
                        row["freshness_status"] = (
                            "future" if age_minutes < -5 else
                            "fresh" if age_minutes <= 24 * 60 else
                            "aging" if age_minutes <= 72 * 60 else "stale"
                        )
                    except (TypeError, ValueError, OverflowError):
                        row["freshness_status"] = "unknown"
                        row["newest_age_minutes"] = None
                row["freshness_threshold_hours"] = 72
                source_health.append(row)
            brief_digest = sha256(_canonical(brief_data)).hexdigest()
            event_ledger = self._append_event_ledger(brief_data, brief_digest, started)
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
                    "source_health": source_health,
                },
                "context": {
                    "market": self.context.market,
                    "symbol": self.context.symbol,
                    "venue": self.context.venue,
                    "timeframe": self.context.timeframe,
                },
                "brief": brief_data,
                "brief_sha256": brief_digest,
                "event_ledger": event_ledger,
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
            "event_ledger": {"schema_version": "hes.news_event_record.v1", "status": "BLOCKED",
                             "records_appended": 0, "records_total": None},
        }
        self._atomic_write(snapshot)
        return snapshot

    def run_forever(self, stop_event: Event) -> None:
        # Fixed start-to-start cadence without overlapping polls or catch-up bursts.
        next_run = time.monotonic()
        while not stop_event.is_set():
            delay = max(0.0, next_run - time.monotonic())
            if delay and stop_event.wait(delay):
                break
            if stop_event.is_set():
                break
            try:
                self.poll_once()
            except Exception as exc:
                try:
                    self.record_failure(exc)
                except Exception:
                    # The dashboard still fails closed if persistence itself is unavailable.
                    self.last_status = "BLOCKED"
                    self.last_error = "SNAPSHOT_PERSISTENCE_FAILED"
            next_run += self.interval_seconds
            if next_run <= time.monotonic():
                next_run = time.monotonic() + self.interval_seconds

    def read_snapshot(self, *, max_age_seconds: int | None = None) -> dict:
        raw = self.snapshot_path.read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError("news monitor snapshot exceeds size limit")
        snapshot = json.loads(raw.decode("utf-8"))
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("news monitor snapshot schema mismatch")
        snapshot_digest = snapshot.get("snapshot_sha256")
        unsigned_snapshot = dict(snapshot)
        unsigned_snapshot.pop("snapshot_sha256", None)
        if not isinstance(snapshot_digest, str) or sha256(_canonical(unsigned_snapshot)).hexdigest() != snapshot_digest:
            raise ValueError("news monitor snapshot digest mismatch")
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

    def _append_event_ledger(self, brief: dict, brief_digest: str, observed_at: datetime) -> dict:
        """Persist each source item once for later Gate.io candle-window attribution."""
        ledger_name = f"news_events_{observed_at.year}.jsonl"
        ledger_path = self.snapshot_path.with_name(ledger_name)
        provenance = brief.get("provenance", {})
        evidence_by_url = {
            row.get("url"): row for row in provenance.get("source_evidence", [])
            if isinstance(row, dict) and isinstance(row.get("url"), str)
        }
        cluster_by_item = {
            row.get("item_id"): row.get("event_cluster_id")
            for row in provenance.get("event_cluster_assignments", [])
            if isinstance(row, dict) and isinstance(row.get("item_id"), str)
        }
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(ledger_path, os.O_CREAT | os.O_RDWR | os.O_APPEND, 0o640)
        appended = 0
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            if os.fstat(fd).st_size > 50_000_000:
                raise ValueError("news event ledger exceeds 50 MB safety limit")
            os.lseek(fd, 0, os.SEEK_SET)
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
            seen = set()
            if raw:
                for line_number, line in enumerate(raw.splitlines(), 1):
                    try:
                        record = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise ValueError(f"news event ledger line {line_number} is invalid") from exc
                    digest = record.pop("record_sha256", None)
                    if not isinstance(digest, str) or sha256(_canonical(record)).hexdigest() != digest:
                        raise ValueError(f"news event ledger line {line_number} digest mismatch")
                    event_id = record.get("event_id")
                    if not isinstance(event_id, str) or not event_id:
                        raise ValueError(f"news event ledger line {line_number} event id missing")
                    seen.add(event_id)
            for finding in brief.get("findings", []):
                if not isinstance(finding, dict):
                    continue
                event_id = finding.get("item_id")
                if not isinstance(event_id, str) or not event_id or event_id in seen:
                    continue
                evidence = evidence_by_url.get(finding.get("url"), {})
                record = {
                    "schema_version": "hes.news_event_record.v1",
                    "event_id": event_id,
                    "event_cluster_id": cluster_by_item.get(event_id),
                    "first_seen_at": observed_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "published_at": finding.get("published_at"),
                    "source_id": evidence.get("source_id"),
                    "source": finding.get("source"),
                    "url": finding.get("url"),
                    "feed_payload_sha256": evidence.get("feed_payload_sha256"),
                    "raw_item_sha256": evidence.get("raw_item_sha256"),
                    "retrieved_at": evidence.get("retrieved_at"),
                    "brief_sha256": brief_digest,
                    "title": finding.get("title"),
                    "impact": finding.get("impact"),
                    "relevance": finding.get("relevance"),
                    "directional_bias": finding.get("directional_bias"),
                    "categories": finding.get("categories", []),
                    "freshness": finding.get("freshness"),
                    "caveats": finding.get("caveats", []),
                }
                record["record_sha256"] = sha256(_canonical(record)).hexdigest()
                os.write(fd, _canonical(record) + b"\n")
                seen.add(event_id)
                appended += 1
            os.fsync(fd)
            return {
                "schema_version": "hes.news_event_record.v1",
                "status": "OK",
                "path": ledger_name,
                "records_appended": appended,
                "records_total": len(seen),
                "last_append_at": observed_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _atomic_write(self, snapshot: dict) -> None:
        snapshot.pop("snapshot_sha256", None)
        snapshot["snapshot_sha256"] = sha256(_canonical(snapshot)).hexdigest()
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
