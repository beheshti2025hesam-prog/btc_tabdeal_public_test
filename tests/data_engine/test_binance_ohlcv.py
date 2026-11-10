from __future__ import annotations

from urllib.parse import urlparse, parse_qs

import pytest

from core.data_engine.binance_ohlcv import (
    BinanceOHLCVError,
    fetch_closed_candles,
)


def kline(open_ms: int, close_ms: int, close: str = "101.10") -> list:
    return [
        open_ms, "100.00", "102.00", "99.00", close, "12.3400",
        close_ms, "1234.5678", 42, "6.0", "600.0", "0",
    ]


def test_spot_uses_official_native_kline_endpoint_and_preserves_precision():
    captured = {}

    def transport(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return [kline(0, 899_999)]

    candles = fetch_closed_candles(
        symbol="BTCUSDT", interval="15m", limit=10, market_type="spot",
        now_ms=900_001, transport=transport,
    )

    parsed = urlparse(captured["url"])
    assert parsed.scheme == "https"
    assert parsed.netloc == "api.binance.com"
    assert parsed.path == "/api/v3/klines"
    assert parse_qs(parsed.query) == {
        "symbol": ["BTCUSDT"], "interval": ["15m"], "limit": ["10"]
    }
    assert captured["timeout"] == 8.0
    assert len(candles) == 1
    assert candles[0].close == "101.10"
    assert candles[0].volume == "12.3400"
    assert candles[0].quote_volume == "1234.5678"
    assert candles[0].is_closed is True
    assert candles[0].as_dict()["open_time_utc"].endswith("+00:00")


def test_usdm_uses_futures_kline_endpoint():
    captured = {}

    def transport(url, _timeout):
        captured["url"] = url
        return [kline(0, 899_999)]

    assert len(fetch_closed_candles(
        market_type="usdm", now_ms=900_001, transport=transport
    )) == 1
    parsed = urlparse(captured["url"])
    assert parsed.netloc == "fapi.binance.com"
    assert parsed.path == "/fapi/v1/klines"


def test_forming_candle_is_excluded_and_gaps_are_not_fabricated():
    rows = [
        kline(0, 899_999),
        kline(1_800_000, 2_699_999),
        kline(2_700_000, 3_599_999),
    ]
    candles = fetch_closed_candles(now_ms=3_000_000, transport=lambda *_: rows)
    assert [c.open_time_ms for c in candles] == [0, 1_800_000]
    assert all(c.is_closed for c in candles)


@pytest.mark.parametrize("kwargs", [
    {"market_type": "tabdeal"},
    {"symbol": "btc/usdt"},
    {"interval": "17m"},
    {"limit": 0},
    {"limit": 1001},
    {"limit": True},
])
def test_rejects_invalid_request_parameters(kwargs):
    with pytest.raises(ValueError):
        fetch_closed_candles(
            now_ms=10_000_000, transport=lambda *_: [], **kwargs
        )


def test_rejects_malformed_payload():
    with pytest.raises(BinanceOHLCVError):
        fetch_closed_candles(
            now_ms=10_000_000, transport=lambda *_: {"data": []}
        )


def test_rejects_out_of_order_candles():
    with pytest.raises(BinanceOHLCVError):
        fetch_closed_candles(
            now_ms=10_000_000,
            transport=lambda *_: [kline(900_000, 1_799_999), kline(0, 899_999)],
        )


def test_never_calls_transport_for_invalid_symbol():
    def should_not_run(*_):
        raise AssertionError("transport must not run for invalid input")

    with pytest.raises(ValueError):
        fetch_closed_candles(symbol="BTC USDT", transport=should_not_run)
