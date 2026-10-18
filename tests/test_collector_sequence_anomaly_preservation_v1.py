import json

import pytest

from forward.forward_tabdeal_collector_v1 import (
    ForwardTabdealCollectorV1,
    normalize_trade,
)


def payload(sequence):
    return {
        "type": "trade",
        "data": {
            "symbol": "BTC_USDT",
            "price": "100",
            "amount": "1",
            "sequence": sequence,
            "side": "buy",
            "updated": "2026-10-18T00:00:00+00:00",
        },
    }


@pytest.mark.parametrize(
    "sequence",
    [True, False, 1.9, float("nan"), float("inf"), -1, " 1", "1.0", "٧"],
)
def test_collector_rejects_coerced_sequence_values(sequence):
    with pytest.raises(ValueError, match="sequence"):
        normalize_trade(payload(sequence))


def test_collector_accepts_ascii_digit_string_sequence():
    record = normalize_trade(payload("123"))
    assert record is not None
    assert record["sequence"] == 123


def test_repeated_sequence_is_persisted_with_diagnostic(tmp_path):
    collector = ForwardTabdealCollectorV1(str(tmp_path / "observations.jsonl"), enabled=True)
    first = {"sequence": 10, "symbol": "BTC_USDT", "price": 100.0, "amount": 1.0}
    repeated = dict(first)

    assert collector._persist_sequence_observation(first) == "INCREASING_SEQUENCE"
    assert collector._persist_sequence_observation(repeated) == "REPEATED_OR_NON_INCREASING_SEQUENCE"
    rows = [json.loads(line) for line in (tmp_path / "observations.jsonl").read_text().splitlines()]

    assert len(rows) == 2
    assert rows[0]["collector_sequence_status"] == "INCREASING_SEQUENCE"
    assert rows[1]["collector_sequence_status"] == "REPEATED_OR_NON_INCREASING_SEQUENCE"
    assert rows[1]["collector_last_accepted_sequence"] == 10
    assert collector.last_sequence == 10


def test_out_of_order_sequence_is_preserved_without_rewinding_state(tmp_path):
    collector = ForwardTabdealCollectorV1(str(tmp_path / "observations.jsonl"), enabled=True)
    first = {"sequence": 12, "symbol": "BTC_USDT", "price": 100.0, "amount": 1.0}
    late = {"sequence": 11, "symbol": "BTC_USDT", "price": 99.0, "amount": 1.0}

    collector._persist_sequence_observation(first)
    assert collector._persist_sequence_observation(late) == "REPEATED_OR_NON_INCREASING_SEQUENCE"
    rows = [json.loads(line) for line in (tmp_path / "observations.jsonl").read_text().splitlines()]

    assert [row["sequence"] for row in rows] == [12, 11]
    assert rows[1]["collector_sequence_status"] == "REPEATED_OR_NON_INCREASING_SEQUENCE"
    assert collector.last_sequence == 12
