from datetime import datetime, timezone
import math
import pytest
from forward.tabdeal_readonly_adapter_v1 import parse_trade_frame

ASOF = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)


def base():
    return {
        "type": "trade", "symbol": "BTC_USDT", "price": "100",
        "amount": "0.1", "side": "buy", "sequence": 7,
        "timestamp": 1791356400000,
    }


def test_normalizes_frame():
    result = parse_trade_frame(base(), as_of=ASOF)
    assert result["source"] == "tabdeal_ws_forward_v1"
    assert result["sequence"] == 7


def test_rejects_future():
    frame = base()
    frame["timestamp"] = 1791356401000
    with pytest.raises(ValueError, match="future"):
        parse_trade_frame(frame, as_of=ASOF)


def test_rejects_scope_and_incomplete():
    frame = base()
    frame["symbol"] = "ETH_USDT"
    with pytest.raises(ValueError):
        parse_trade_frame(frame, as_of=ASOF)
    frame = base()
    del frame["sequence"]
    with pytest.raises(ValueError):
        parse_trade_frame(frame, as_of=ASOF)


def test_rejects_bad_values():
    for key, value in [("price", "0"), ("amount", "-1"), ("side", "hold"), ("sequence", -1)]:
        frame = base()
        frame[key] = value
        with pytest.raises(ValueError):
            parse_trade_frame(frame, as_of=ASOF)


@pytest.mark.parametrize("sequence", [
    True, False, 1.9, float("nan"), float("inf"), -1, " 7", "7.0", "", "٧",
])
def test_rejects_coerced_or_non_ascii_sequence_values(sequence):
    frame = base()
    frame["sequence"] = sequence
    with pytest.raises(ValueError, match="sequence"):
        parse_trade_frame(frame, as_of=ASOF)


def test_accepts_ascii_digit_string_without_coercion():
    frame = base()
    frame["sequence"] = "007"
    result = parse_trade_frame(frame, as_of=ASOF)
    assert result["sequence"] == 7
