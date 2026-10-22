from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal

import pytest

from forward.native_ohlcv_websocket_v1 import NativeKlineStreamError, parse_kline_event


def payload(*, closed=True, symbol="BTCUSDT", interval="1m", close=None):
    now = int(time.time() * 1000)
    step = 60_000 if interval == "1m" else 3_600_000
    start = (now // step - 1) * step
    kline = {
        "t": start, "T": start + step - 1, "s": symbol, "i": interval,
        "o": "100.10", "c": close or "101.20", "h": "102.00", "l": "99.50",
        "v": "12.3400", "n": 8, "q": "1234.50", "V": "4.20",
        "Q": "420.00", "B": "0", "x": closed,
    }
    return json.dumps({
        "stream": f"{symbol.lower()}@kline_{interval}",
        "data": {"e": "kline", "E": now, "s": symbol, "k": kline},
    }, separators=(",", ":"))


def test_closed_event_uses_canonical_candle_and_exact_payload_hash():
    raw = payload(closed=True)
    parsed = parse_kline_event(raw, symbol="BTCUSDT", interval="1m")
    assert parsed.candle is not None
    assert parsed.candle.venue == "binance"
    assert parsed.candle.product == "spot"
    assert parsed.candle.symbol == "BTCUSDT"
    assert parsed.candle.closed is True
    assert parsed.candle.open == Decimal("100.10")
    assert parsed.candle.volume == Decimal("12.3400")
    assert parsed.payload_sha256 == hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_open_event_is_validated_but_not_admitted_as_closed_candle():
    parsed = parse_kline_event(payload(closed=False), symbol="BTCUSDT", interval="1m")
    assert parsed.candle is None
    assert len(parsed.payload_sha256) == 64


def test_rejects_wrong_symbol_and_interval():
    with pytest.raises(NativeKlineStreamError, match="unexpected_event_or_symbol"):
        parse_kline_event(payload(), symbol="ETHUSDT", interval="1m")
    with pytest.raises(NativeKlineStreamError, match="invalid_kline_identity"):
        parse_kline_event(payload(), symbol="BTCUSDT", interval="5m")


def test_rejects_non_string_or_malformed_stream_identity():
    with pytest.raises(NativeKlineStreamError, match="invalid_stream_identity"):
        parse_kline_event(payload(), symbol=123, interval="1m")
    with pytest.raises(NativeKlineStreamError, match="invalid_stream_identity"):
        parse_kline_event(payload(), symbol="btcusdt", interval="1m")
    wrong_stream = json.loads(payload())
    wrong_stream["stream"] = "ethusdt@kline_1m"
    with pytest.raises(NativeKlineStreamError, match="invalid_stream_identity"):
        parse_kline_event(json.dumps(wrong_stream), symbol="BTCUSDT", interval="1m")


def test_rejects_invalid_ohlc_and_non_kline_payload():
    bad = json.loads(payload())
    bad["data"]["k"]["h"] = "90"
    with pytest.raises(NativeKlineStreamError, match="invalid_kline_candle"):
        parse_kline_event(json.dumps(bad), symbol="BTCUSDT", interval="1m")
    with pytest.raises(NativeKlineStreamError, match="unexpected_event_or_symbol"):
        parse_kline_event(json.dumps({"e": "trade", "s": "BTCUSDT", "E": 1}),
                          symbol="BTCUSDT", interval="1m")


def test_rejects_malformed_json_and_non_text_payload():
    with pytest.raises(NativeKlineStreamError, match="invalid_json"):
        parse_kline_event("{", symbol="BTCUSDT", interval="1m")
    with pytest.raises(NativeKlineStreamError, match="invalid_payload_type"):
        parse_kline_event(object(), symbol="BTCUSDT", interval="1m")
