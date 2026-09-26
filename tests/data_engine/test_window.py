from datetime import datetime, timedelta, timezone

import pytest

from core.data_engine.window import IntelligenceWindow, validate_window_alignment


def test_window_accepts_exact_utc_duration():
    start = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    window = IntelligenceWindow("BTC_USDT", 60, start, start + timedelta(seconds=60))
    assert window.symbol == "BTC_USDT"


def test_window_rejects_naive_timestamp():
    start = datetime(2026, 9, 26, 12, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        IntelligenceWindow("BTC_USDT", 60, start, start + timedelta(seconds=60))


def test_window_rejects_wrong_duration():
    start = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="duration"):
        IntelligenceWindow("BTC_USDT", 60, start, start + timedelta(seconds=30))


def test_window_rejects_non_positive_timeframe():
    start = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="timeframe_seconds"):
        IntelligenceWindow("BTC_USDT", 0, start, start + timedelta(seconds=60))


def test_alignment_rejects_symbol_mismatch():
    start = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    window = IntelligenceWindow("BTC_USDT", 60, start, start + timedelta(seconds=60))
    with pytest.raises(ValueError, match="symbol"):
        validate_window_alignment(window=window, symbol="ETH_USDT",
                                   timeframe_seconds=60, start=start,
                                   end=start + timedelta(seconds=60))


def test_alignment_rejects_timeframe_mismatch():
    start = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    window = IntelligenceWindow("BTC_USDT", 60, start, start + timedelta(seconds=60))
    with pytest.raises(ValueError, match="timeframe"):
        validate_window_alignment(window=window, symbol="BTC_USDT",
                                   timeframe_seconds=300, start=start,
                                   end=start + timedelta(seconds=60))


def test_alignment_rejects_window_boundary_mismatch():
    start = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    window = IntelligenceWindow("BTC_USDT", 60, start, start + timedelta(seconds=60))
    with pytest.raises(ValueError, match="window end"):
        validate_window_alignment(window=window, symbol="BTC_USDT",
                                   timeframe_seconds=60, start=start,
                                   end=start + timedelta(seconds=120))


def test_alignment_accepts_equivalent_timezone_offsets():
    start = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    window = IntelligenceWindow("BTC_USDT", 60, start, start + timedelta(seconds=60))
    local_start = datetime(2026, 9, 26, 16, 30,
                           tzinfo=timezone(timedelta(hours=4, minutes=30)))
    local_end = local_start + timedelta(seconds=60)
    validate_window_alignment(window=window, symbol="BTC_USDT",
                               timeframe_seconds=60, start=local_start,
                               end=local_end)
