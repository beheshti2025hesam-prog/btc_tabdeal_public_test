from unittest.mock import patch

import pytest

from tools.binance_public_clock_probe import probe


def test_probe_accepts_fresh_candle_and_synchronized_clock():
    payloads = [
        {"serverTime": 1_800_000_000_000},
        [[1_799_999_940_000, "1", "1", "1", "1", "1",
          1_799_999_999_999, "1", 1, "1", "1", "0"]],
    ]
    with patch("tools.binance_public_clock_probe.time.time_ns",
               side_effect=[1_800_000_000_000_000_000,
                            1_800_000_000_000_000_000]), \
         patch("tools.binance_public_clock_probe.get_json",
               side_effect=payloads):
        result = probe("test", "https://example.invalid", "/time", "/klines")
    assert result.server_local_skew_ms == 0
    assert result.candle_age_ms == 60_000


def test_probe_rejects_future_candle():
    payloads = [
        {"serverTime": 1_800_000_000_000},
        [[1_800_000_001_000, "1", "1", "1", "1", "1",
          1_800_000_059_999, "1", 1, "1", "1", "0"]],
    ]
    with patch("tools.binance_public_clock_probe.time.time_ns",
               side_effect=[1_800_000_000_000_000_000,
                            1_800_000_000_000_000_000]), \
         patch("tools.binance_public_clock_probe.get_json",
               side_effect=payloads):
        with pytest.raises(RuntimeError, match="future"):
            probe("test", "https://example.invalid", "/time", "/klines")


def test_probe_rejects_clock_skew():
    payloads = [{"serverTime": 1_800_000_010_000}]
    with patch("tools.binance_public_clock_probe.time.time_ns",
               side_effect=[1_800_000_000_000_000_000,
                            1_800_000_000_000_000_000]), \
         patch("tools.binance_public_clock_probe.get_json",
               side_effect=payloads):
        with pytest.raises(RuntimeError, match="clock skew"):
            probe("test", "https://example.invalid", "/time", "/klines")
