from __future__ import annotations

import base64
import hashlib
import json

import pytest

from forward.raw_ingress_journal_v1 import RawIngressJournalError, RawIngressJournalV1


def append(journal, raw=b'{"trade":{"sequence":"007"}}', verdict="ACCEPTED", reason=None, generation=1):
    return journal.append(
        event_type="FRAME", received_at_utc="2026-10-11T00:00:00+00:00",
        receive_monotonic_ns=100 + journal.path.stat().st_size if journal.path.exists() else 100,
        connection_generation=generation, verdict=verdict, reason_code=reason,
        raw_bytes=raw,
    )


def test_raw_bytes_are_recoverable_and_hash_pinned(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    raw = b'{"trade":{"sequence":"007"}}'
    event = append(journal, raw=raw)
    stored = json.loads(journal.path.read_text().splitlines()[0])
    assert base64.b64decode(stored["raw_bytes_b64"]) == raw
    assert stored["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert event["event_no"] == 1


def test_rejected_and_duplicate_payloads_are_both_preserved(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    raw = b'{"trade":{"sequence":7}}'
    append(journal, raw=raw, verdict="REJECTED", reason="SCHEMA_INVALID")
    append(journal, raw=raw, verdict="REJECTED", reason="SCHEMA_INVALID")
    events = [json.loads(line) for line in journal.path.read_text().splitlines()]
    assert len(events) == 2
    assert events[0]["raw_sha256"] == events[1]["raw_sha256"]
    assert events[0]["event_sha256"] != events[1]["event_sha256"]


def test_disconnect_and_reconnect_generation_are_explicit(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    journal.append(event_type="DISCONNECT", received_at_utc="2026-10-11T00:00:00+00:00",
                   receive_monotonic_ns=10, connection_generation=1,
                   verdict="DISCONNECTED", reason_code="SOCKET_CLOSED")
    append(journal, generation=2)
    events = [json.loads(line) for line in journal.path.read_text().splitlines()]
    assert events[0]["verdict"] == "DISCONNECTED"
    assert [e["connection_generation"] for e in events] == [1, 2]


def test_partial_trailing_record_fails_closed_without_mutation(tmp_path):
    path = tmp_path / "ingress.jsonl"
    journal = RawIngressJournalV1(path)
    append(journal)
    original = path.read_bytes()
    path.write_bytes(original + b'{"partial":')
    damaged = path.read_bytes()
    with pytest.raises(RawIngressJournalError, match="PARTIAL_TRAILING_RECORD"):
        append(journal)
    assert path.read_bytes() == damaged


def test_tampered_record_fails_closed_without_repair(tmp_path):
    path = tmp_path / "ingress.jsonl"
    journal = RawIngressJournalV1(path)
    append(journal)
    original = path.read_text()
    path.write_text(original.replace("ACCEPTED", "REJECTED", 1))
    damaged = path.read_bytes()
    with pytest.raises(RawIngressJournalError, match="EVENT_HASH_MISMATCH"):
        append(journal)
    assert path.read_bytes() == damaged


def test_invalid_verdict_rejected_before_append(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    with pytest.raises(RawIngressJournalError, match="VERDICT_INVALID"):
        append(journal, verdict="MAYBE")
    assert not journal.path.exists()

def test_non_utc_or_malformed_timestamp_is_rejected_before_append(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    with pytest.raises(RawIngressJournalError, match="UTC_TIMESTAMP_MUST_BE_UTC"):
        journal.append(
            event_type="FRAME", received_at_utc="2026-10-11T01:00:00+01:00",
            receive_monotonic_ns=100, connection_generation=1, verdict="ACCEPTED",
        )
    with pytest.raises(RawIngressJournalError, match="UTC_TIMESTAMP_INVALID"):
        journal.append(
            event_type="FRAME", received_at_utc="not-a-timestamp",
            receive_monotonic_ns=100, connection_generation=1, verdict="ACCEPTED",
        )
    assert not journal.path.exists()


def test_symlinked_lock_file_fails_closed(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    target = tmp_path / "attacker-controlled-lock"
    target.write_bytes(b"do not modify")
    journal.lock_path.symlink_to(target)
    with pytest.raises(OSError):
        append(journal)
    assert target.read_bytes() == b"do not modify"
    assert not journal.path.exists()

