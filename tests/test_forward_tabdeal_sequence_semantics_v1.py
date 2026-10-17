from __future__ import annotations

import hashlib
import json

import pytest

from forward import forward_tabdeal_collector_v1 as collector_module
from forward.forward_tabdeal_collector_v1 import (
    ForwardTabdealCollectorV1,
    normalize_trade,
)


def _message(sequence):
    return json.dumps(
        {
            "trade": {
                "symbol": "BTC_USDT",
                "price": "65000.25",
                "amount": "0.01",
                "side": "buy",
                "updated": "2026-10-13T12:00:00Z",
                "sequence": sequence,
            }
        },
        separators=(",", ":"),
    )


def test_normalizer_preserves_opaque_string_sequence_and_exact_payload_hash():
    raw = _message("00017")
    record = normalize_trade(json.loads(raw), raw_message=raw)

    assert record is not None
    assert record["sequence"] == "00017"
    assert record["sequence_semantics"] == "UNKNOWN_OPAQUE"
    assert record["raw_payload"] == raw
    assert record["raw_payload_sha256"] == hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_normalizer_does_not_require_an_undocumented_sequence_field():
    raw = json.dumps(
        {
            "trade": {
                "symbol": "BTC_USDT",
                "price": 65000,
                "amount": 0.01,
                "updated": "2026-10-13T12:00:00Z",
            }
        }
    )
    record = normalize_trade(json.loads(raw), raw_message=raw)

    assert record is not None
    assert record["sequence"] is None
    assert record["sequence_semantics"] == "UNKNOWN_OPAQUE"


@pytest.mark.parametrize(
    ("price", "amount"),
    [
        ("NaN", "0.01"),
        ("Infinity", "0.01"),
        ("65000", "Infinity"),
        ("-1", "0.01"),
        ("65000", "0"),
        ("not-a-number", "0.01"),
    ],
)
def test_normalizer_rejects_invalid_or_non_finite_trade_numbers(price, amount):
    payload = {
        "trade": {
            "symbol": "BTC_USDT",
            "price": price,
            "amount": amount,
            "updated": "2026-10-13T12:00:00Z",
        }
    }
    assert normalize_trade(payload) is None


def test_collector_keeps_decreasing_sequence_values_instead_of_dropping_them(
    tmp_path, monkeypatch
):
    messages = [_message(7), _message(6), ""]

    class FakeSocket:
        def send(self, _value):
            pass

        def recv(self):
            return messages.pop(0)

        def close(self):
            pass

    monkeypatch.setattr(
        collector_module.websocket,
        "create_connection",
        lambda *_args, **_kwargs: FakeSocket(),
    )
    ticks = iter([0, 0, 0, 0, 0, 20])
    monkeypatch.setattr(collector_module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(collector_module.time, "sleep", lambda _seconds: None)

    output = tmp_path / "observations.jsonl"
    collector = ForwardTabdealCollectorV1(str(output), enabled=True)
    collector.run(run_seconds=10)

    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert [record["sequence"] for record in records] == [7, 6]
    assert all(record["sequence_semantics"] == "UNKNOWN_OPAQUE" for record in records)
    assert [record["raw_payload"] for record in records] == [_message(7), _message(6)]


def test_connection_failure_is_logged_and_collector_reconnects(monkeypatch, caplog):
    attempts = {"count": 0}

    def fail_connection(*_args, **_kwargs):
        attempts["count"] += 1
        raise OSError("synthetic connection failure")

    monkeypatch.setattr(
        collector_module.websocket, "create_connection", fail_connection
    )
    ticks = iter([0, 0, 0, 20])
    monkeypatch.setattr(collector_module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(collector_module.time, "sleep", lambda _seconds: None)

    collector = ForwardTabdealCollectorV1(enabled=True)
    with caplog.at_level("ERROR"):
        collector.run(run_seconds=10)

    assert attempts["count"] == 1
    assert "Forward Tabdeal observation connection failed" in caplog.text


def test_collector_stays_disabled_by_default(tmp_path):
    collector = ForwardTabdealCollectorV1(str(tmp_path / "observations.jsonl"))
    with pytest.raises(RuntimeError, match="disabled by default"):
        collector.run(run_seconds=1)
