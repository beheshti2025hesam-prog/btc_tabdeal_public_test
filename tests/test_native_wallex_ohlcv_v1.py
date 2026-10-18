from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import pytest

from forward.native_wallex_ohlcv_v1 import (
    SUPPORTED_MINUTE_RESOLUTIONS,
    fetch_native_ohlcv,
    fetch_native_ohlcv_evidence,
    parse_history,
)


NOW = datetime(2026, 10, 18, 12, 1, 30, tzinfo=timezone.utc)
PAYLOAD = {
    "s": "ok",
    "t": [1792324800, 1792324860],
    "o": ["100.10", "101.00"],
    "h": ["102.00", "103.00"],
    "l": ["99.00", "100.50"],
    "c": ["101.00", "102.50"],
    "v": ["1.2300", "2.3400"],
}


def test_native_history_preserves_decimal_and_closed_state():
    candles = parse_history(PAYLOAD, symbol="BTCUSDT", timeframe_minutes=1, as_of=NOW)
    assert len(candles) == 2
    assert candles[0].open == Decimal("100.10")
    assert candles[0].volume == Decimal("1.2300")
    assert candles[0].is_closed is True
    assert candles[1].is_closed is False
    assert candles[0].source == "wallex_native_udf_history"
    assert candles[0].open_time.tzinfo is timezone.utc


def test_only_documented_minute_resolutions_are_enabled():
    assert SUPPORTED_MINUTE_RESOLUTIONS == {1, 60, 180, 360, 720}
    for unsupported in (0, 15, 30, 1440, True, "1"):
        with pytest.raises(ValueError, match="resolution|timeframe_minutes"):
            parse_history(PAYLOAD, symbol="BTCUSDT", timeframe_minutes=unsupported, as_of=NOW)


def test_fetch_uses_native_endpoint_and_preserves_raw_hash():
    captured = {}

    def transport(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return json.dumps(PAYLOAD).encode()

    evidence = fetch_native_ohlcv_evidence(
        symbol="BTCUSDT",
        timeframe_minutes=1,
        start=datetime(2026, 10, 18, 11, 59, tzinfo=timezone.utc),
        end=datetime(2026, 10, 18, 12, 2, tzinfo=timezone.utc),
        as_of=NOW,
        transport=transport,
        clock=lambda: NOW,
    )
    assert "api.wallex.ir/v1/udf/history?" in captured["url"]
    assert "symbol=BTCUSDT" in captured["url"]
    assert "resolution=1" in captured["url"]
    assert captured["timeout"] == 10.0
    assert evidence.raw_response == json.dumps(PAYLOAD).encode()
    assert evidence.raw_sha256 == sha256(evidence.raw_response).hexdigest()
    assert evidence.retrieved_at == NOW
    assert evidence.server_date_header is None  # injected transport intentionally has no HTTP headers
    assert evidence.server_clock_offset_seconds is None
    assert len(evidence.candles) == 2


def test_compatibility_fetch_returns_candles():
    candles = fetch_native_ohlcv(
        symbol="BTCUSDT",
        timeframe_minutes=1,
        start=datetime(2026, 10, 18, 11, 59, tzinfo=timezone.utc),
        end=datetime(2026, 10, 18, 12, 2, tzinfo=timezone.utc),
        as_of=NOW,
        transport=lambda _url, _timeout: json.dumps(PAYLOAD).encode(),
    )
    assert len(candles) == 2


@pytest.mark.parametrize("field", ["t", "o", "h", "l", "c", "v"])
def test_rejects_mismatched_columns(field):
    payload = dict(PAYLOAD)
    payload[field] = payload[field][:-1]
    with pytest.raises(ValueError, match="length mismatch"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=1, as_of=NOW)


def test_rejects_non_monotonic_timestamps():
    payload = dict(PAYLOAD)
    payload["t"] = [1792324860, 1792324800]
    with pytest.raises(ValueError, match="strictly increasing"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=1, as_of=NOW)


@pytest.mark.parametrize("timestamp", [True, False, "1792324800", 1792324800.0, 0, -1])
def test_rejects_non_integer_or_invalid_timestamps(timestamp):
    payload = dict(PAYLOAD)
    payload["t"] = [timestamp, 1792324860]
    with pytest.raises(ValueError, match="timestamp"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=1, as_of=NOW)


def test_rejects_misaligned_timestamp():
    payload = dict(PAYLOAD)
    payload["t"] = [1792324801, 1792324860]
    with pytest.raises(ValueError, match="timeframe-aligned"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=1, as_of=NOW)


def test_rejects_malformed_ohlc():
    payload = dict(PAYLOAD)
    payload["h"] = ["98", "103"]
    with pytest.raises(ValueError, match="inconsistent OHLC"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=1, as_of=NOW)


@pytest.mark.parametrize("bad_value", [True, None, "NaN", "Infinity", "not-a-number"])
def test_rejects_invalid_numeric_values(bad_value):
    payload = dict(PAYLOAD)
    payload["c"] = [bad_value, "102.50"]
    with pytest.raises(ValueError):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=1, as_of=NOW)


def test_rejects_negative_volume_and_nonpositive_prices():
    payload = dict(PAYLOAD)
    payload["v"] = ["-0.1", "2.34"]
    with pytest.raises(ValueError, match="volume"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=1, as_of=NOW)
    payload = dict(PAYLOAD)
    payload["o"] = ["0", "101"]
    with pytest.raises(ValueError, match="prices"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=1, as_of=NOW)


def test_rejects_bad_status_and_naive_datetime():
    payload = dict(PAYLOAD)
    payload["s"] = "no_data"
    with pytest.raises(ValueError, match="status"):
        parse_history(payload, symbol="BTCUSDT", timeframe_minutes=1, as_of=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_history(PAYLOAD, symbol="BTCUSDT", timeframe_minutes=1, as_of=datetime(2026, 10, 18))
