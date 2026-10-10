from datetime import datetime, timedelta, timezone
import json

import pytest

from forward.observation_supervisor_v1 import (
    ForwardObservationSupervisorV1,
    SupervisorError,
)


class FakeClock:
    def __init__(self):
        self.seconds = 1000
        self.base = datetime(2026, 10, 10, tzinfo=timezone.utc)

    def monotonic_ns(self):
        return self.seconds * 1_000_000_000

    def utc_now(self):
        return self.base + timedelta(seconds=self.seconds)

    def advance(self, seconds):
        self.seconds += seconds


def supervisor(tmp_path, clock, run_id="run-a", boot_id="boot-a"):
    return ForwardObservationSupervisorV1(
        tmp_path, run_id=run_id, boot_id=boot_id,
        utc_now=clock.utc_now, monotonic_ns=clock.monotonic_ns,
    )


def test_start_heartbeat_stop_records_durable_hash_chain(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    started = s.start()
    clock.advance(10)
    heartbeat = s.heartbeat(healthy=True)
    stopped = s.stop()
    assert started["event_type"] == "SESSION_STARTED"
    assert heartbeat["event_type"] == "HEARTBEAT"
    assert stopped["event_type"] == "SESSION_STOPPED"
    lines = (tmp_path / "supervisor_events.jsonl").read_text().splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["event_no"] for line in lines] == [1, 2, 3]
    assert all(len(json.loads(line)["event_sha256"]) == 64 for line in lines)


def test_exclusive_process_lock_rejects_overlapping_writer(tmp_path):
    clock = FakeClock()
    first = supervisor(tmp_path, clock, "run-a")
    second = supervisor(tmp_path, clock, "run-b")
    first.start()
    try:
        with pytest.raises(SupervisorError, match="WRITER_ALREADY_HELD"):
            second.start()
    finally:
        first.close()
        second.close()


def test_unclosed_prior_run_is_explicitly_interrupted_on_next_start(tmp_path):
    clock = FakeClock()
    first = supervisor(tmp_path, clock, "run-a")
    first.start()
    clock.advance(10)
    first.heartbeat(healthy=True)
    first.close()  # Simulates process exit without a graceful stop marker.

    second = supervisor(tmp_path, clock, "run-b")
    second.start()
    events = [json.loads(line) for line in (tmp_path / "supervisor_events.jsonl").read_text().splitlines()]
    interruptions = [e for e in events if e["event_type"] == "INTERRUPTION"]
    assert len(interruptions) == 1
    assert interruptions[0]["run_id"] == "run-a"
    assert interruptions[0]["details"]["reason_code"] == "PRIOR_SESSION_UNCLOSED"
    second.stop()


def test_unhealthy_heartbeat_invalidates_run_and_blocks_future_heartbeats(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    s.heartbeat(healthy=False, reason_code="SOURCE_STALE")
    with pytest.raises(SupervisorError, match="SESSION_ALREADY_INTERRUPTED"):
        s.heartbeat(healthy=True)
    s.stop()
    report = s.continuity_report(required_seconds=1, max_heartbeat_gap_seconds=30)
    assert not report["proven"]
    assert report["reason"] == "INTERRUPTION_RECORDED"


def test_continuity_proof_requires_duration_and_bounded_heartbeat_gaps(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    clock.advance(10)
    s.heartbeat(healthy=True)
    clock.advance(10)
    s.heartbeat(healthy=True)
    clock.advance(1)
    s.stop()
    report = s.continuity_report(required_seconds=20, max_heartbeat_gap_seconds=15)
    assert report["proven"]
    assert report["continuous_seconds"] == 21


def test_continuity_fails_when_heartbeat_gap_exceeds_bound(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    clock.advance(10)
    s.heartbeat(healthy=True)
    clock.advance(31)
    s.stop()
    report = s.continuity_report(required_seconds=20, max_heartbeat_gap_seconds=15)
    assert not report["proven"]
    assert report["reason"] == "HEARTBEAT_GAP_EXCEEDED"


def test_continuity_fails_on_boot_id_change(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock, boot_id="boot-a")
    s.start()
    clock.advance(1)
    s.heartbeat(healthy=True)
    s.close()
    # A separate run after reboot has a different boot identity and must not
    # be interpreted as continuity with the first run.
    next_clock = FakeClock()
    next_clock.advance(2)
    next_run = supervisor(tmp_path, next_clock, run_id="run-b", boot_id="boot-b")
    next_run.start()
    old = supervisor(tmp_path, next_clock, run_id="run-a", boot_id="boot-a")
    report = old.continuity_report(required_seconds=1, max_heartbeat_gap_seconds=30)
    assert not report["proven"]
    assert report["reason"] == "INTERRUPTION_RECORDED"
    next_run.stop()


def test_duplicate_run_id_is_rejected_without_appending(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock, "same")
    s.start()
    s.stop()
    before = (tmp_path / "supervisor_events.jsonl").read_bytes()
    duplicate = supervisor(tmp_path, clock, "same")
    with pytest.raises(SupervisorError, match="RUN_ID_REUSE_FORBIDDEN"):
        duplicate.start()
    assert (tmp_path / "supervisor_events.jsonl").read_bytes() == before


def test_tampered_or_partial_journal_fails_closed_and_is_preserved(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    s.close()
    path = tmp_path / "supervisor_events.jsonl"
    original = path.read_text()
    path.write_text(original.replace("SESSION_STARTED", "SESSION_TAMPERED"))
    tampered = path.read_text()
    next_run = supervisor(tmp_path, clock, "run-b")
    with pytest.raises(SupervisorError, match="JOURNAL_DIGEST_MISMATCH"):
        next_run.start()
    assert path.read_text() == tampered


def test_continuity_requires_durable_stop_marker(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    clock.advance(21)
    s.heartbeat(healthy=True)
    report = s.continuity_report(required_seconds=20, max_heartbeat_gap_seconds=30)
    assert not report["proven"]
    assert report["reason"] == "SESSION_NOT_STOPPED_OR_DUPLICATE_STOP"
    s.stop()


def test_continuity_fails_when_interruption_write_fails_but_stop_succeeds(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    clock.advance(10)
    s.heartbeat(healthy=True)
    clock.advance(10)
    s.heartbeat(healthy=True)
    original_append = s._append

    def fail_interruption(events, *, event_type, run_id, details=None):
        if event_type == "INTERRUPTION":
            raise SupervisorError("JOURNAL_DURABLE_WRITE_FAILED")
        return original_append(events, event_type=event_type, run_id=run_id, details=details)

    s._append = fail_interruption
    with pytest.raises(SupervisorError, match="JOURNAL_DURABLE_WRITE_FAILED"):
        s.interrupt("SIMULATED_DISK_ERROR")
    s._append = original_append
    s.stop()
    report = s.continuity_report(required_seconds=20, max_heartbeat_gap_seconds=15)
    assert not report["proven"]
    assert report["reason"] == "INTERRUPTION_RECORDED"


@pytest.mark.parametrize(
    "invalid_limit",
    [float("nan"), float("inf"), float("-inf"), True, 0, -1],
)
def test_continuity_rejects_non_finite_or_invalid_limits(tmp_path, invalid_limit):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    with pytest.raises(SupervisorError, match="CONTINUITY_LIMIT_INVALID"):
        s.continuity_report(required_seconds=invalid_limit)
    with pytest.raises(SupervisorError, match="CONTINUITY_LIMIT_INVALID"):
        s.continuity_report(max_heartbeat_gap_seconds=invalid_limit)
    s.stop()


def test_invalid_clock_and_configuration_fail_closed(tmp_path):
    with pytest.raises(SupervisorError, match="BOOT_ID_REQUIRED"):
        ForwardObservationSupervisorV1(tmp_path, run_id="x", boot_id="")
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    with pytest.raises(SupervisorError, match="CONTINUITY_LIMIT_INVALID"):
        s.continuity_report(required_seconds=0)
    s.stop()
