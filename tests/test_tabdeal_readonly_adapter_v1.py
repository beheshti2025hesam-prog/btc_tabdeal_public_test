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


def test_normalizes_frame_and_marks_sequence_opaque():
    r = parse_trade_frame(base(), as_of=ASOF)
    assert r["source"] == "tabdeal_ws_forward_v1"
    assert r["sequence"] == 7
    assert r["sequence_semantics"] == "UNKNOWN_OPAQUE"


def test_preserves_opaque_string_sequence_without_integer_cast():
    x = base()
    x["sequence"] = "0007"
    r = parse_trade_frame(x, as_of=ASOF)
    assert r["sequence"] == "0007"
    assert r["sequence_semantics"] == "UNKNOWN_OPAQUE"


def test_missing_sequence_is_preserved_as_unknown_for_downstream_gate():
    x = base()
    del x["sequence"]
    r = parse_trade_frame(x, as_of=ASOF)
    assert r["sequence"] is None
    assert r["sequence_semantics"] == "UNKNOWN_OPAQUE"


def test_rejects_future():
    x = base()
    x["timestamp"] = 1791356401000
    with pytest.raises(ValueError, match="future"):
        parse_trade_frame(x, as_of=ASOF)


def test_rejects_scope_and_incomplete_core_fields():
    x = base()
    x["symbol"] = "ETH_USDT"
    with pytest.raises(ValueError):
        parse_trade_frame(x, as_of=ASOF)
    x = base()
    del x["price"]
    with pytest.raises(ValueError):
        parse_trade_frame(x, as_of=ASOF)


def test_rejects_bad_values():
    for key, val in [("price", "0"), ("amount", "-1"), ("side", "hold")]:
        x = base()
        x[key] = val
        with pytest.raises(ValueError):
            parse_trade_frame(x, as_of=ASOF)
