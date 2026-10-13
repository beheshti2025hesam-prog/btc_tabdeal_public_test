"""Adversarial timestamp validation for the forward observation supervisor."""
from datetime import datetime, timedelta, timezone
import hashlib
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

    def utc_now(self):
        return self.base + timedelta(seconds=self.seconds)

    def monotonic_ns(self):
        return self.seconds * 1_000_000_000


def _rewrite_first_event_timestamp(path, timestamp):
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    events[0]["at_utc"] = timestamp
    previous = None
    lines = []
    for event in events:
        event["previous_event_sha256"] = previous
        body = {key: value for key, value in event.items() if key != "event_sha256"}
        event["event_sha256"] = hashlib.sha256(
            json.dumps(
                body, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        previous = event["event_sha256"]
        lines.append(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _seed_journal(tmp_path, clock):
    session = ForwardObservationSupervisorV1(
        tmp_path, run_id="seed-run", boot_id="boot-a",
        utc_now=clock.utc_now, monotonic_ns=clock.monotonic_ns,
    )
    session.start()
    session.close()
    return tmp_path / "supervisor_events.jsonl"


def test_naive_utc_clock_fails_closed_before_journal_write(tmp_path):
    session = ForwardObservationSupervisorV1(
        tmp_path, run_id="naive-clock-run", boot_id="boot-a",
        utc_now=lambda: datetime(2026, 10, 10),
        monotonic_ns=lambda: 1_000_000_000,
    )
    with pytest.raises(SupervisorError, match="UTC_CLOCK_MUST_BE_TIMEZONE_AWARE"):
        session.start()
    assert not (tmp_path / "supervisor_events.jsonl").exists()


@pytest.mark.parametrize(
    "bad_timestamp",
    [
        "not-a-timestamp",
        "2026-10-10T00:00:00",
        "2026-02-30T00:00:00+00:00",
    ],
)
def test_invalid_or_timezone_naive_journal_timestamp_fails_closed_and_preserves_bytes(
    tmp_path, bad_timestamp
):
    clock = FakeClock()
    path = _seed_journal(tmp_path, clock)
    _rewrite_first_event_timestamp(path, bad_timestamp)
    before = path.read_bytes()

    verifier = ForwardObservationSupervisorV1(
        tmp_path, run_id="verify-run", boot_id="boot-a",
        utc_now=clock.utc_now, monotonic_ns=clock.monotonic_ns,
    )
    with pytest.raises(SupervisorError, match="JOURNAL_EVENT_SCHEMA_INVALID"):
        verifier.start()
    assert path.read_bytes() == before


def test_hash_valid_future_timestamp_beyond_skew_margin_fails_closed(tmp_path):
    clock = FakeClock()
    path = _seed_journal(tmp_path, clock)
    future = (clock.utc_now() + timedelta(seconds=6)).isoformat()
    _rewrite_first_event_timestamp(path, future)
    before = path.read_bytes()

    verifier = ForwardObservationSupervisorV1(
        tmp_path, run_id="verify-run", boot_id="boot-a",
        utc_now=clock.utc_now, monotonic_ns=clock.monotonic_ns,
    )
    with pytest.raises(SupervisorError, match="JOURNAL_TIMESTAMP_IN_FUTURE"):
        verifier.start()
    assert path.read_bytes() == before


def test_hash_valid_timestamp_within_five_second_clock_skew_is_accepted(tmp_path):
    clock = FakeClock()
    path = _seed_journal(tmp_path, clock)
    within_skew = (clock.utc_now() + timedelta(seconds=5)).isoformat()
    _rewrite_first_event_timestamp(path, within_skew)

    verifier = ForwardObservationSupervisorV1(
        tmp_path, run_id="verify-run", boot_id="boot-a",
        utc_now=clock.utc_now, monotonic_ns=clock.monotonic_ns,
    )
    started = verifier.start()
    assert started["event_type"] == "SESSION_STARTED"
    verifier.stop()
