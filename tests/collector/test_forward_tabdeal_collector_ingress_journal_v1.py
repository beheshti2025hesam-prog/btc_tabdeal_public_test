from __future__ import annotations

import base64
import json

import pytest

from forward.forward_tabdeal_collector_v1 import ForwardTabdealCollectorV1


def valid_payload(sequence=7, price="65000"):
    return json.dumps(
        {"trade": {
            "symbol": "BTC_USDT", "price": price, "amount": "0.01",
            "side": "buy", "sequence": sequence, "updated": "2026-10-10T23:59:00Z",
        }},
        separators=(",", ":"),
    ).encode()


def read_events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_real_forward_collector_journals_raw_frame_before_output(tmp_path):
    output = tmp_path / "observations.jsonl"
    collector = ForwardTabdealCollectorV1(str(output))
    raw = valid_payload(sequence="007")

    collector._process_message(raw, generation=3)

    journal_path = tmp_path / "observations.raw_ingress.jsonl"
    events = read_events(journal_path)
    assert len(events) == 1
    assert events[0]["verdict"] == "ACCEPTED"
    assert events[0]["connection_generation"] == 3
    assert base64.b64decode(events[0]["raw_bytes_b64"]) == raw
    assert events[0]["details"]["sequence_semantics"] == "OPAQUE_UNVERIFIED"
    assert len(output.read_text().splitlines()) == 1


def test_malformed_frame_is_preserved_as_rejected_without_output(tmp_path):
    output = tmp_path / "observations.jsonl"
    collector = ForwardTabdealCollectorV1(str(output))
    raw = b'{"trade":'

    collector._process_message(raw, generation=1)

    event = read_events(tmp_path / "observations.raw_ingress.jsonl")[0]
    assert event["verdict"] == "REJECTED"
    assert event["reason_code"] == "JSON_DECODE_ERROR"
    assert base64.b64decode(event["raw_bytes_b64"]) == raw
    assert not output.exists()


def test_non_monotonic_sequence_is_journaled_as_ignored_not_erased(tmp_path):
    output = tmp_path / "observations.jsonl"
    collector = ForwardTabdealCollectorV1(str(output))
    collector._process_message(valid_payload(sequence=7, price="65000"), generation=1)
    collector._process_message(valid_payload(sequence=7, price="65001"), generation=1)

    events = read_events(tmp_path / "observations.raw_ingress.jsonl")
    assert [event["verdict"] for event in events] == ["ACCEPTED", "IGNORED"]
    assert events[1]["reason_code"] == "NON_MONOTONIC_SEQUENCE"
    assert events[1]["details"]["sequence_semantics"] == "OPAQUE_UNVERIFIED"
    assert len(output.read_text().splitlines()) == 1


def test_journal_failure_blocks_real_collector_output_handoff(tmp_path):
    class BrokenJournal:
        def append(self, **kwargs):
            raise OSError("journal unavailable")

    output = tmp_path / "observations.jsonl"
    collector = ForwardTabdealCollectorV1(str(output), raw_ingress_journal=BrokenJournal())
    with pytest.raises(OSError, match="journal unavailable"):
        collector._process_message(valid_payload(), generation=1)
    assert not output.exists()


def test_run_records_connection_lifecycle_for_actual_collector(monkeypatch, tmp_path):
    import forward.forward_tabdeal_collector_v1 as module

    class FakeSocket:
        def send(self, value):
            assert value == "BTC_USDT"

        def recv(self):
            return valid_payload()

        def close(self):
            self.closed = True

    socket = FakeSocket()
    monkeypatch.setattr(module.websocket, "create_connection", lambda *args, **kwargs: socket)
    clock = iter([0.0, 0.0, 0.0, 2.0, 2.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    output = tmp_path / "observations.jsonl"
    collector = ForwardTabdealCollectorV1(str(output), enabled=True)
    collector.run(run_seconds=1)

    events = read_events(tmp_path / "observations.raw_ingress.jsonl")
    assert [event["event_type"] for event in events] == ["CONNECTED", "FRAME", "DISCONNECT"]
    assert [event["connection_generation"] for event in events] == [1, 1, 1]
    assert events[1]["verdict"] == "ACCEPTED"
    assert len(output.read_text().splitlines()) == 1


def test_output_persistence_failure_is_explicitly_journaled(monkeypatch, tmp_path):
    output = tmp_path / "observations.jsonl"
    collector = ForwardTabdealCollectorV1(str(output))

    def fail_append(_record):
        raise OSError("output disk unavailable")

    monkeypatch.setattr(collector, "_append", fail_append)
    with pytest.raises(OSError, match="output disk unavailable"):
        collector._process_message(valid_payload(), generation=2)

    events = read_events(tmp_path / "observations.raw_ingress.jsonl")
    assert [event["event_type"] for event in events] == ["FRAME", "HANDOFF_FAILURE"]
    assert [event["verdict"] for event in events] == ["ACCEPTED", "REJECTED"]
    assert events[1]["reason_code"] == "OUTPUT_PERSISTENCE_FAILED"
    assert events[1]["details"]["error_type"] == "OSError"
    assert not output.exists()


def test_trade_shaped_schema_drift_is_preserved_as_rejected(tmp_path):
    output = tmp_path / "observations.jsonl"
    collector = ForwardTabdealCollectorV1(str(output))
    raw = b'{"trade":{"symbol":"BTC_USDT","price":"65000"}}'

    collector._process_message(raw, generation=2)

    event = read_events(tmp_path / "observations.raw_ingress.jsonl")[0]
    assert event["verdict"] == "REJECTED"
    assert event["reason_code"] == "TRADE_SCHEMA_INVALID"
    assert base64.b64decode(event["raw_bytes_b64"]) == raw
    assert not output.exists()


def test_empty_websocket_payload_is_preserved_not_silently_dropped(tmp_path):
    output = tmp_path / "observations.jsonl"
    collector = ForwardTabdealCollectorV1(str(output))
    raw = b""

    collector._process_message(raw, generation=4)

    event = read_events(tmp_path / "observations.raw_ingress.jsonl")[0]
    assert event["verdict"] == "REJECTED"
    assert event["reason_code"] == "JSON_DECODE_ERROR"
    assert base64.b64decode(event["raw_bytes_b64"]) == raw
    assert not output.exists()
