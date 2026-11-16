from datetime import datetime, timezone
import pytest

from forward.tabdeal_readonly_adapter_v1 import parse_trade_frame

ASOF = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)


def base():
    return {
        "type": "trade",
        "symbol": "BTC_USDT",
        "price": "100",
        "amount": "0.1",
        "side": "buy",
        "sequence": 7,
        "timestamp": 1791356400000,
    }


def test_normalizes_frame_and_preserves_native_sequence():
    result = parse_trade_frame(base(), as_of=ASOF)
    assert result["source"] == "tabdeal_ws_forward_v1"
    assert result["sequence"] == 7


def test_missing_sequence_is_optional_metadata():
    frame = base()
    del frame["sequence"]
    result = parse_trade_frame(frame, as_of=ASOF)
    assert result["sequence"] is None


def test_generic_aliases_are_not_assumed_to_be_tabdeal_sequence():
    frame = base()
    del frame["sequence"]
    frame["seq"] = 7
    result = parse_trade_frame(frame, as_of=ASOF)
    assert result["sequence"] is None


def test_rejects_future():
    frame = base()
    frame["timestamp"] = 1791356401000
    with pytest.raises(ValueError, match="future"):
        parse_trade_frame(frame, as_of=ASOF)


def test_rejects_scope_and_incomplete_core_trade():
    frame = base()
    frame["symbol"] = "ETH_USDT"
    with pytest.raises(ValueError):
        parse_trade_frame(frame, as_of=ASOF)
    frame = base()
    del frame["price"]
    with pytest.raises(ValueError):
        parse_trade_frame(frame, as_of=ASOF)


def test_rejects_bad_values():
    for key, value in [("price", "0"), ("amount", "-1"), ("side", "hold")]:
        frame = base()
        frame[key] = value
        with pytest.raises(ValueError):
            parse_trade_frame(frame, as_of=ASOF)


def test_preserves_opaque_sequence_values_without_numeric_assumptions():
    for value in (-1, "0007", True, 1.5, [], {}, ""):
        frame = base()
        frame["sequence"] = value
        assert parse_trade_frame(frame, as_of=ASOF)["sequence"] == value
