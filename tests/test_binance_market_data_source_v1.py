import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from forward.binance_market_data_source_v1 import (
    BinanceMarketDataError, parse_kline_event, websocket_url,
)
from forward.native_candle_bridge_v1 import normalize_native_candles


def event(*, symbol="BTCUSDT", interval="1m", closed=False):
    step = 60_000 if interval == "1m" else 3_600_000
    start = 1_800_000_000_000
    start -= start % step
    k = {
        "t": start, "T": start + step - 1, "s": symbol, "i": interval,
        "f": 100, "L": 200, "o": "100.10", "c": "101.20",
        "h": "102.00", "l": "99.50", "v": "12.3400", "n": 8,
        "x": closed, "q": "1234.50", "V": "4.20", "Q": "420.00", "B": "0",
    }
    return json.dumps({"stream": f"{symbol.lower()}@kline_{interval}",
                       "data": {"e": "kline", "E": start + 10, "s": symbol, "k": k}})


def test_parse_spot_stream_preserves_decimal_identity_and_open_status():
    parsed = parse_kline_event(event(), market="spot", symbol="BTCUSDT", interval="1m")
    assert parsed.market == "spot"
    assert parsed.symbol == "BTCUSDT"
    assert parsed.candle.venue == "binance"
    assert parsed.candle.source == "binance_websocket_kline"
    assert parsed.candle.open == Decimal("100.10")
    assert parsed.candle.volume == Decimal("12.3400")
    assert parsed.candle.is_closed is False
    assert len(parsed.payload_sha256) == 64


def test_parse_closed_usdm_futures_event_keeps_market_separate():
    parsed = parse_kline_event(event(closed=True), market="usdm_futures",
                               symbol="BTCUSDT", interval="1m")
    assert parsed.market == "usdm_futures"
    assert parsed.candle.is_closed is True


def test_closed_stream_candle_flows_through_existing_canonical_bridge():
    parsed = parse_kline_event(event(closed=True), market="spot",
                               symbol="BTCUSDT", interval="1m")
    batch = normalize_native_candles(
        [parsed.candle], venue="binance", market="spot",
        as_of=datetime.fromtimestamp((parsed.candle.close_time_ms + 1) / 1000, timezone.utc),
    )
    assert batch.identity.venue == "binance"
    assert batch.identity.market == "spot"
    assert batch.identity.symbol == "BTCUSDT"
    assert batch.identity.timeframe_seconds == 60
    assert batch.identity.source == "binance_websocket_kline"
    assert batch.candles[0].open == Decimal("100.10")


def test_open_stream_candle_is_not_admitted_to_closed_candle_bridge():
    parsed = parse_kline_event(event(closed=False), market="spot",
                               symbol="BTCUSDT", interval="1m")
    with pytest.raises(ValueError, match="no_fully_closed_candles"):
        normalize_native_candles(
            [parsed.candle], venue="binance", market="spot",
            as_of=datetime.fromtimestamp((parsed.candle.close_time_ms + 1) / 1000, timezone.utc),
        )


def test_rejects_wrong_symbol_and_interval_in_stream():
    with pytest.raises(BinanceMarketDataError, match="symbol_or_event_time"):
        parse_kline_event(event(), market="spot", symbol="ETHUSDT", interval="1m")
    with pytest.raises(BinanceMarketDataError, match="identity_or_finality"):
        parse_kline_event(event(), market="spot", symbol="BTCUSDT", interval="1h")


def test_rejects_bad_ohlc_and_non_kline_event():
    bad = json.loads(event())
    bad["data"]["k"]["h"] = "90"
    with pytest.raises(BinanceMarketDataError, match="invalid_ohlc_range"):
        parse_kline_event(json.dumps(bad), market="spot", symbol="BTCUSDT", interval="1m")
    with pytest.raises(BinanceMarketDataError, match="unexpected_websocket_event"):
        parse_kline_event(json.dumps({"e": "trade"}), market="spot", symbol="BTCUSDT", interval="1m")


def test_urls_select_exact_market_and_symbol_stream():
    assert websocket_url(market="spot", symbol="BTCUSDT", interval="1m") == (
        "wss://data-stream.binance.vision/ws/btcusdt@kline_1m"
    )
    assert websocket_url(market="usdm_futures", symbol="BTCUSDT", interval="1h") == (
        "wss://fstream.binance.com/market/ws/btcusdt@kline_1h"
    )
    with pytest.raises(BinanceMarketDataError, match="supported_intervals"):
        websocket_url(market="spot", symbol="BTCUSDT", interval="15m")
