from datetime import datetime, timezone
from decimal import Decimal
import json
import pytest

from forward.native_wallex_ohlcv_v1 import fetch_native_ohlcv, parse_history


NOW = datetime(2026, 10, 18, 12, 20, tzinfo=timezone.utc)
PAYLOAD = {
    "s": "ok",
    "t": [1792324800, 1792325700],
    "o": ["100.10", "101.00"],
    "h": ["102.00", "103.00"],
    "l": ["99.00", "100.50"],
    "c": ["101.00", "102.50"],
    "v": ["1.2300", "2.3400"],
}


def test_native_history_preserves_decimal_and_closed_state():
    candles = parse_history(PAYLOAD, symbol="BTCUSDT", timeframe_minutes=15, as_of=NOW)
    assert len(candles) == 2
    assert candles[0].open == Decimal("100.10")
    assert candles[0].volume == Decimal("1.2300")
    assert candles[0].is_closed is True
    assert candles[1].is_closed is False
    assert candles[0].source == "wallex_native_udf_history"


def test_fetch_uses_official_native_history_and_injected_transport():
    captured = {}

    def transport(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return json.dumps(PAYLOAD).encode()

    candles = fetch_native_ohlcv(
        symbol="BTCUSDT",
        timeframe_minutes=15,
        start=datetime(2026, 10, 18, 11, 55, tzinfo=timezone.utc),
        end=datetime(2026, 10, 18, 12, 20, tzinfo=timezone.utc),
        as_of=NOW,
        transport=transport,
    )
    assert "api.wallex.ir/v1/udf/history?" in captured["url"]
    assert "symbol=BTCUSDT" in captured["url"]
    assert "resolution=15" in captured["url"]
    assert len(candles) == 2


@pytest.mark.parametrize("field", ["t", "o", "h", "l", "c", "v"])
def test_rejects_mismatched_columns(field):
    payload = dict(PAYLOAD)
    payload[field] = payload[field][:-1]
    with pytest.raises(ValueError, match="length mismatch"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=15, as_of=NOW)


def test_rejects_non_monotonic_timestamps():
    payload = dict(PAYLOAD)
    payload["t"] = [1792325700, 1792324800]
    with pytest.raises(ValueError, match="strictly increasing"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=15, as_of=NOW)


def test_rejects_malformed_ohlc():
    payload = dict(PAYLOAD)
    payload["h"] = ["98", "103"]
    with pytest.raises(ValueError, match="inconsistent OHLC"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=15, as_of=NOW)


def test_rejects_naive_as_of():
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_history(PAYLOAD, symbol="BTCUSDT", timeframe_minutes=15, as_of=datetime(2026, 10, 18))
