import pytest

from forward.forward_tabdeal_collector_v1 import normalize_trade


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


@pytest.mark.parametrize("sequence", [True, False, 1.9, float("nan"), float("inf"), -1, " 1", "1.0"])
def test_collector_rejects_coerced_sequence_values(sequence):
    with pytest.raises(ValueError, match="sequence"):
        normalize_trade(payload(sequence))


def test_collector_accepts_ascii_digit_string_sequence():
    record = normalize_trade(payload("123"))
    assert record is not None
    assert record["sequence"] == 123
