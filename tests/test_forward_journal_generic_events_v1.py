import json
import threading

import pytest

from forward.forward_journal_v1 import ForwardJournalV1


def event(event_id, decision="PAPER_CANDIDATE"):
    return {"event_id": event_id, "schema": decision, "decision": decision}


def test_generic_writer_appends_mixed_immutable_events_and_is_idempotent(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    assert writer.append_event(event("candidate-1")) is True
    assert writer.append_event(event("outcome-1", "PAPER_OUTCOME")) is True
    assert writer.append_event(event("candidate-1")) is False
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["event_id"] for row in rows] == ["candidate-1", "outcome-1"]


def test_decision_writer_reuses_generic_integrity_contract(tmp_path):
    writer = ForwardJournalV1(tmp_path / "journal.jsonl")
    row = {
        "event_id": "decision-1", "observed_at": "2026-11-01T10:00:00Z",
        "symbol": "BTC_USDT", "timeframe": "15m", "decision": "NO_TRADE",
        "evidence_source": ["gateio_public_spot"],
    }
    writer.append_decision(row)
    saved = json.loads(writer.path.read_text())
    assert saved["outcome"] is None and saved["closed_at"] is None


def test_duplicate_concurrent_generic_appends_are_idempotent(tmp_path):
    writer = ForwardJournalV1(tmp_path / "journal.jsonl")
    results = []
    threads = [threading.Thread(target=lambda: results.append(writer.append_event(event("same")))) for _ in range(12)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert results.count(True) == 1
    assert results.count(False) == 11
    assert len(writer.path.read_text().splitlines()) == 1


@pytest.mark.parametrize("payload,message", [
    (b'{"event_id":"legacy"}\n{bad json\n', "malformed JSON"),
    (b'{"event_id":"legacy"}\n\n', "blank record"),
    (b'{"event_id":"legacy"}', "incomplete trailing record"),
    (b'[]\n', "not an object"),
    (b'{"event_id":"x"}\n{"event_id":"x"}\n', "duplicate event_id"),
])
def test_corrupt_or_ambiguous_history_fails_closed_without_mutation(tmp_path, payload, message):
    path = tmp_path / "journal.jsonl"
    path.write_bytes(payload)
    before = path.read_bytes()
    with pytest.raises(ValueError, match=message):
        ForwardJournalV1(path).append_event(event("new"))
    assert path.read_bytes() == before


def test_legacy_rows_without_event_id_are_preserved_but_new_rows_need_ids(tmp_path):
    path = tmp_path / "journal.jsonl"
    path.write_text('{"schema":"legacy-paper-row"}\n', encoding="utf-8")
    writer = ForwardJournalV1(path)
    assert writer.append_event(event("new-event")) is True
    with pytest.raises(ValueError, match="event_id is required"):
        writer.append_event({"schema": "new-without-id"})


def test_oversized_record_fails_closed(tmp_path):
    writer = ForwardJournalV1(tmp_path / "journal.jsonl")
    with pytest.raises(ValueError, match="size limit"):
        writer.append_event({"event_id": "large", "payload": "x" * (1024 * 1024)})
