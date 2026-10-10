from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from forward.observation_supervisor_v1 import (
    ForwardObservationSupervisorV1,
    SourceHealthEvidence,
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


def healthy_evidence(clock, **overrides):
    values = {
        "schema_version": "hes_source_health_evidence_v1",
        "venue": "tabdeal", "product": "futures",
        "endpoint": "special_margin/broadcast", "topic": "trade",
        "expected_symbol": "BTC_USDT", "observed_symbol": "BTC_USDT",
        "connection_id": "test-connection-1", "session_generation": 1,
        "source_event_at": clock.utc_now(), "received_at": clock.utc_now(),
        "max_age_seconds": 30.0, "schema_valid": True, "reason_code": "SOURCE_HEALTHY",
    }
    values.update(overrides)
    return SourceHealthEvidence(**values)


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
    heartbeat = s.heartbeat(evidence=healthy_evidence(clock))
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
    first.heartbeat(evidence=healthy_evidence(clock))
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
    stale = healthy_evidence(clock, source_event_at=clock.utc_now() - timedelta(seconds=120))
    event = s.heartbeat(evidence=stale)
    assert event["event_type"] == "INTERRUPTION"
    assert event["details"]["reason_code"] == "SOURCE_EVENT_STALE"
    with pytest.raises(SupervisorError, match="SESSION_ALREADY_INTERRUPTED"):
        s.heartbeat(evidence=healthy_evidence(clock))
    s.stop()
    report = s.continuity_report(required_seconds=1, max_heartbeat_gap_seconds=30)
    assert not report["proven"]
    assert report["reason"] == "INTERRUPTION_RECORDED"


def test_continuity_proof_requires_duration_and_bounded_heartbeat_gaps(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    clock.advance(10)
    s.heartbeat(evidence=healthy_evidence(clock))
    clock.advance(10)
    s.heartbeat(evidence=healthy_evidence(clock))
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
    s.heartbeat(evidence=healthy_evidence(clock))
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
    s.heartbeat(evidence=healthy_evidence(clock))
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


def test_journal_rejects_missing_required_field_even_when_digest_is_recomputed(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    s.close()
    path = tmp_path / "supervisor_events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    del first["boot_id"]
    body = {key: value for key, value in first.items() if key != "event_sha256"}
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    first["event_sha256"] = hashlib.sha256(canonical).hexdigest()
    lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tampered = path.read_bytes()

    next_run = supervisor(tmp_path, clock, "run-b")
    with pytest.raises(SupervisorError, match="JOURNAL_EVENT_SCHEMA_INVALID"):
        next_run.start()
    assert path.read_bytes() == tampered


def test_journal_rejects_boolean_event_number_even_when_digest_is_recomputed(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    s.close()
    path = tmp_path / "supervisor_events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["event_no"] = True  # bool compares equal to integer 1 in Python.
    body = {key: value for key, value in first.items() if key != "event_sha256"}
    canonical = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    first["event_sha256"] = hashlib.sha256(canonical).hexdigest()
    lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tampered = path.read_bytes()

    next_run = supervisor(tmp_path, clock, "run-b")
    with pytest.raises(SupervisorError, match="JOURNAL_SEQUENCE_INVALID"):
        next_run.start()
    assert path.read_bytes() == tampered


def test_continuity_requires_durable_stop_marker(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    clock.advance(21)
    s.heartbeat(evidence=healthy_evidence(clock))
    report = s.continuity_report(required_seconds=20, max_heartbeat_gap_seconds=30)
    assert not report["proven"]
    assert report["reason"] == "SESSION_NOT_STOPPED_OR_DUPLICATE_STOP"
    s.stop()


def test_continuity_fails_when_interruption_write_fails_but_stop_succeeds(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    clock.advance(10)
    s.heartbeat(evidence=healthy_evidence(clock))
    clock.advance(10)
    s.heartbeat(evidence=healthy_evidence(clock))
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



def _rewrite_as_hash_valid_journal(path, event_types, *, event_numbers=None, run_ids=None, heartbeat_details=None):
    """Rewrite a synthetic journal with valid hashes but deliberately bad semantics."""
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == len(event_types)
    if event_numbers is not None:
        assert len(event_numbers) == len(events)
    if run_ids is not None:
        assert len(run_ids) == len(events)
    previous = None
    rewritten = []
    for index, (event, event_type) in enumerate(zip(events, event_types), start=1):
        event["event_no"] = event_numbers[index - 1] if event_numbers is not None else index
        if run_ids is not None:
            event["run_id"] = run_ids[index - 1]
        event["event_type"] = event_type
        event["previous_event_sha256"] = previous
        if event_type == "SESSION_STOPPED":
            event["details"] = {"reason_code": "TEST_STOP", "interrupted": False}
        elif event_type == "HEARTBEAT":
            event["details"] = dict(heartbeat_details) if heartbeat_details is not None else {
                "source_health": "HEALTHY", "reason_code": "TEST"
            }
        elif event_type == "SESSION_STARTED":
            event["details"] = {"mode": "OBSERVATION_ONLY", "decision": "NO_TRADE_ONLY", "execution_enabled": False}
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        event["event_sha256"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        ).hexdigest()
        previous = event["event_sha256"]
        rewritten.append(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    # Independently confirm the rewritten chain itself is cryptographically valid.
    previous = None
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        assert event["previous_event_sha256"] == previous
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        assert hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        ).hexdigest() == event["event_sha256"]
        previous = event["event_sha256"]


@pytest.mark.parametrize(
    ("event_types", "expected_error"),
    [
        (["HEARTBEAT", "SESSION_STARTED", "SESSION_STOPPED"], "JOURNAL_EVENT_RUN_MISMATCH"),
        (["SESSION_STARTED", "SESSION_STOPPED", "HEARTBEAT"], "JOURNAL_EVENT_RUN_MISMATCH"),
    ],
)
def test_hash_valid_but_semantically_invalid_journal_is_rejected_and_preserved(
    tmp_path, event_types, expected_error
):
    clock = FakeClock()
    s = supervisor(tmp_path, clock, run_id="source-run")
    s.start()
    clock.advance(1)
    s.heartbeat(evidence=healthy_evidence(clock))
    clock.advance(1)
    s.stop()

    path = tmp_path / "supervisor_events.jsonl"
    _rewrite_as_hash_valid_journal(path, event_types)
    before = path.read_bytes()
    # Verify the adversarial fixture is not merely a broken hash-chain test.
    assert len(before) > 0

    verifier = supervisor(tmp_path, clock, run_id="new-run")
    with pytest.raises(SupervisorError, match=expected_error):
        verifier.start()
    assert path.read_bytes() == before



@pytest.mark.parametrize(
    ("event_numbers", "expected_error"),
    [
        ([1, 1, 3], "JOURNAL_SEQUENCE_INVALID"),
        ([1, 3, 2], "JOURNAL_SEQUENCE_INVALID"),
    ],
)
def test_hash_valid_journal_with_duplicate_or_reordered_event_numbers_is_rejected_and_preserved(
    tmp_path, event_numbers, expected_error
):
    clock = FakeClock()
    s = supervisor(tmp_path, clock, run_id="source-run")
    s.start()
    clock.advance(1)
    s.heartbeat(evidence=healthy_evidence(clock))
    clock.advance(1)
    s.stop()

    path = tmp_path / "supervisor_events.jsonl"
    _rewrite_as_hash_valid_journal(
        path,
        ["SESSION_STARTED", "HEARTBEAT", "SESSION_STOPPED"],
        event_numbers=event_numbers,
    )
    before = path.read_bytes()
    verifier = supervisor(tmp_path, clock, run_id="new-run")
    with pytest.raises(SupervisorError, match=expected_error):
        verifier.start()
    assert path.read_bytes() == before


def test_hash_valid_cross_run_event_interleaving_is_rejected_and_preserved(tmp_path):
    clock = FakeClock()
    s = supervisor(tmp_path, clock, run_id="source-run")
    s.start()
    clock.advance(1)
    s.heartbeat(evidence=healthy_evidence(clock))
    clock.advance(1)
    s.stop()

    path = tmp_path / "supervisor_events.jsonl"
    _rewrite_as_hash_valid_journal(
        path,
        ["SESSION_STARTED", "HEARTBEAT", "SESSION_STOPPED"],
        run_ids=["source-run", "other-run", "source-run"],
    )
    before = path.read_bytes()
    verifier = supervisor(tmp_path, clock, run_id="new-run")
    with pytest.raises(SupervisorError, match="JOURNAL_EVENT_RUN_MISMATCH"):
        verifier.start()
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "heartbeat_details",
    [
        {"source_health": "UNHEALTHY", "reason_code": "TEST"},
        {"reason_code": "TEST"},
        {"source_health": None, "reason_code": "TEST"},
        {"source_health": "HEALTHY", "reason_code": ""},
        {"source_health": "HEALTHY", "reason_code": 7},
    ],
)
def test_hash_valid_journal_rejects_invalid_heartbeat_semantics_and_preserves_bytes(
    tmp_path, heartbeat_details
):
    clock = FakeClock()
    s = supervisor(tmp_path, clock, run_id="source-run")
    s.start()
    clock.advance(1)
    s.heartbeat(evidence=healthy_evidence(clock))
    clock.advance(1)
    s.stop()

    path = tmp_path / "supervisor_events.jsonl"
    _rewrite_as_hash_valid_journal(
        path,
        ["SESSION_STARTED", "HEARTBEAT", "SESSION_STOPPED"],
        heartbeat_details=heartbeat_details,
    )
    before = path.read_bytes()
    verifier = supervisor(tmp_path, clock, run_id="new-run")
    with pytest.raises(SupervisorError, match="JOURNAL_HEARTBEAT_(SOURCE_HEALTH|REASON)_INVALID"):
        verifier.start()
    assert path.read_bytes() == before
    with pytest.raises(SupervisorError, match="JOURNAL_HEARTBEAT_(SOURCE_HEALTH|REASON)_INVALID"):
        verifier.continuity_report(required_seconds=1, max_heartbeat_gap_seconds=30)
    assert path.read_bytes() == before


@pytest.mark.parametrize("legacy_health", [True, False, 1, "true", None, [], {}])
def test_caller_asserted_health_is_rejected_without_journal_mutation(
    tmp_path, legacy_health
):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    before = (tmp_path / "supervisor_events.jsonl").read_bytes()
    with pytest.raises(SupervisorError, match="STRUCTURED_SOURCE_EVIDENCE_REQUIRED"):
        s.heartbeat(healthy=legacy_health)
    assert (tmp_path / "supervisor_events.jsonl").read_bytes() == before
    s.stop()


@pytest.mark.parametrize("invalid_reason", ["", "  ", 7, None, "x" * 121])
def test_heartbeat_reason_code_cannot_be_missing_or_malformed(
    tmp_path, invalid_reason
):
    clock = FakeClock()
    s = supervisor(tmp_path, clock)
    s.start()
    before = (tmp_path / "supervisor_events.jsonl").read_bytes()
    evidence = healthy_evidence(clock, reason_code=invalid_reason)
    with pytest.raises(SupervisorError, match="SOURCE_HEALTH_REASON_INVALID"):
        s.heartbeat(evidence=evidence)
    assert (tmp_path / "supervisor_events.jsonl").read_bytes() == before
    s.stop()
