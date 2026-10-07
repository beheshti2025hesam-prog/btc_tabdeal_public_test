from __future__ import annotations

import json
import threading

import pytest

from forward.forward_journal_v1 import ForwardJournalV1


def record(event_id: str):
    return {
        "event_id": event_id,
        "observed_at": "2026-10-07T10:00:00+00:00",
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "decision": "NO_TRADE",
        "evidence_source": ["test:baseline"],
    }


def test_duplicate_check_and_append_are_single_writer(tmp_path):
    journal = ForwardJournalV1(tmp_path / "observations.jsonl")
    errors = []

    def writer():
        try:
            journal.append_decision(record("same-event"))
        except ValueError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=writer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    lines = journal.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert sum(error == "duplicate event_id" for error in errors) == 7


def test_malformed_existing_journal_fails_closed(tmp_path):
    path = tmp_path / "observations.jsonl"
    path.write_text('{"event_id":"ok"}
{"broken":
', encoding="utf-8")

    with pytest.raises(ValueError, match="malformed JSON"):
        ForwardJournalV1(path).append_decision(record("new-event"))


def test_append_is_valid_json_and_outcome_is_immutable(tmp_path):
    journal = ForwardJournalV1(tmp_path / "observations.jsonl")
    journal.append_decision(record("event-1"))

    saved = json.loads(journal.path.read_text(encoding="utf-8"))
    assert saved["event_id"] == "event-1"
    assert saved["outcome"] is None
    assert saved["closed_at"] is None

    with pytest.raises(NotImplementedError):
        journal.append_outcome(
            event_id="event-1", outcome="WIN", closed_at="2026-10-07T11:00:00+00:00"
        )
