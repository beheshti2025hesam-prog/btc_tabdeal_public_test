from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import pytest

from forward.raw_ingress_journal_v1 import RawIngressJournalV1
from forward.tabdeal_transport_v1 import TabdealReadOnlyTransportV1


class FakeSocket:
    def send(self, value):
        self.sent = value

    def close(self):
        self.closed = True


def make_transport(tmp_path, records=None, generation=1, journal=None):
    return TabdealReadOnlyTransportV1(
        as_of_provider=lambda: datetime(2026, 10, 11, tzinfo=timezone.utc),
        on_record=(records if records is not None else []).append,
        ws_factory=lambda *args, **kwargs: FakeSocket(),
        raw_ingress_journal=journal or RawIngressJournalV1(tmp_path / "ingress.jsonl"),
        connection_generation=generation,
    )


def read_events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def valid_payload(sequence=7, price="65000", updated="2026-10-10T23:59:00Z"):
    return json.dumps({"trade": {
        "symbol": "BTC_USDT", "price": price, "amount": "0.01",
        "side": "buy", "sequence": sequence, "updated": updated,
    }}, separators=(",", ":")).encode()


def test_transport_journals_exact_raw_bytes_before_handoff(tmp_path):
    records = []
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    transport = make_transport(tmp_path, records=records, journal=journal)
    raw = valid_payload(sequence="007")
    transport._message(None, raw)

    events = read_events(journal.path)
    assert len(events) == 1
    assert events[0]["verdict"] == "ACCEPTED"
    assert base64.b64decode(events[0]["raw_bytes_b64"]) == raw
    assert len(records) == 1
    assert events[0]["details"]["sequence_semantics"] == "OPAQUE_UNVERIFIED"


def test_invalid_json_is_raw_preserved_as_rejected(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    transport = make_transport(tmp_path, journal=journal)
    raw = b'{"trade":'
    transport._message(None, raw)
    event = read_events(journal.path)[0]
    assert event["verdict"] == "REJECTED"
    assert base64.b64decode(event["raw_bytes_b64"]) == raw
    assert event["reason_code"] == "JSONDecodeError"


def test_unsupported_envelope_is_raw_preserved_as_ignored(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    transport = make_transport(tmp_path, journal=journal)
    raw = b'{"heartbeat":true}'
    transport._message(None, raw)
    event = read_events(journal.path)[0]
    assert event["verdict"] == "IGNORED"
    assert base64.b64decode(event["raw_bytes_b64"]) == raw


def test_same_opaque_sequence_with_different_payloads_is_not_auto_conflict(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    transport = make_transport(tmp_path, journal=journal)
    transport._message(None, valid_payload(sequence=7, price="65000"))
    transport._message(None, valid_payload(sequence=7, price="65001"))
    events = read_events(journal.path)
    assert [event["verdict"] for event in events] == ["ACCEPTED", "ACCEPTED"]
    assert events[0]["raw_sha256"] != events[1]["raw_sha256"]


def test_disconnect_is_recorded_and_generation_is_scoped(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    transport = make_transport(tmp_path, generation=4, journal=journal)
    transport._close(None, 1006, "connection lost")
    event = read_events(journal.path)[0]
    assert event["event_type"] == "DISCONNECT"
    assert event["verdict"] == "DISCONNECTED"
    assert event["connection_generation"] == 4


def test_journal_failure_blocks_downstream_handoff(tmp_path):
    class BrokenJournal:
        def append(self, **kwargs):
            raise OSError("journal unavailable")

    records = []
    transport = make_transport(tmp_path, records=records, journal=BrokenJournal())
    with pytest.raises(OSError, match="journal unavailable"):
        transport._message(None, valid_payload())
    assert records == []


def test_missing_required_field_is_preserved_as_schema_rejection(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    transport = make_transport(tmp_path, journal=journal)
    raw = json.dumps({"trade": {
        "symbol": "BTC_USDT", "price": "65000", "amount": "0.01",
        "side": "buy", "updated": "2026-10-10T23:59:00Z",
    }}, separators=(",", ":")).encode()
    transport._message(None, raw)
    event = read_events(journal.path)[0]
    assert event["verdict"] == "REJECTED"
    assert base64.b64decode(event["raw_bytes_b64"]) == raw


def test_opaque_sequence_jump_does_not_claim_missing_message(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    transport = make_transport(tmp_path, journal=journal)
    transport._message(None, valid_payload(sequence=7))
    transport._message(None, valid_payload(sequence=9))
    events = read_events(journal.path)
    assert [event["verdict"] for event in events] == ["ACCEPTED", "ACCEPTED"]
    assert all(event["details"]["sequence_semantics"] == "OPAQUE_UNVERIFIED" for event in events)


def test_connection_error_is_journaled_without_exception_text(tmp_path):
    journal = RawIngressJournalV1(tmp_path / "ingress.jsonl")
    transport = make_transport(tmp_path, generation=5, journal=journal)
    transport._error(None, RuntimeError("secret-like details should not be persisted"))
    event = read_events(journal.path)[0]
    assert event["verdict"] == "CONNECTION_ERROR"
    assert event["reason_code"] == "WEBSOCKET_ERROR"
    assert event["details"] == {"error_type": "RuntimeError"}
