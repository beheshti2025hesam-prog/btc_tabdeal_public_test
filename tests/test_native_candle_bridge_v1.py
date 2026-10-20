from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from forward.native_candle_bridge_v1 import normalize_native_candles, to_feature_candles
from core.feature_engine.ema import EMACalculator

UTC = timezone.utc
AS_OF = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


@dataclass
class WallexLike:
    symbol: str
    timeframe_minutes: int
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool = True
    source: str = "wallex_native_udf_history"


@dataclass
class BinanceLike:
    market: str
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def wallex(start, *, close=None, is_closed=True):
    return WallexLike(
        "BTCUSDT", 1, start, start + timedelta(minutes=1),
        Decimal("100.10"), Decimal("101"), Decimal("99"),
        Decimal(str(close if close is not None else "100.20")),
        Decimal("12.34567890123456789"), is_closed,
    )


def test_wallex_shape_normalizes_without_sequence_and_preserves_decimal():
    start = AS_OF - timedelta(minutes=3)
    batch = normalize_native_candles([wallex(start)], venue="wallex",
                                     market="spot", as_of=AS_OF)
    assert batch.identity.symbol == "BTCUSDT"
    assert batch.candles[0].volume == Decimal("12.34567890123456789")
    assert batch.gaps == ()
    feature = to_feature_candles(batch)
    assert feature[0].trade_count is None
    assert feature[0].volume is None
    with pytest.raises(ValueError, match="wallex_volume_semantics_unresolved"):
        to_feature_candles(batch, include_volume=True)


def test_binance_shape_normalizes_millisecond_fields():
    start = AS_OF - timedelta(minutes=3)
    candle = BinanceLike(
        "spot", "BTCUSDT", "1m", int(start.timestamp() * 1000),
        int((start + timedelta(minutes=1)).timestamp() * 1000) - 1,
        Decimal("100"), Decimal("101"), Decimal("99"),
        Decimal("100.5"), Decimal("5.25"),
    )
    batch = normalize_native_candles([candle], venue="binance",
                                     market="spot", as_of=AS_OF)
    assert batch.candles[0].start == start
    assert batch.candles[0].end == start + timedelta(minutes=1)
    assert batch.identity.timeframe_seconds == 60
    assert to_feature_candles(batch)[0].volume is None
    assert to_feature_candles(batch, include_volume=True)[0].volume == 5.25


def test_open_candle_is_discarded_and_all_open_fails_closed():
    start = AS_OF - timedelta(seconds=30)
    with pytest.raises(ValueError, match="no_fully_closed_candles"):
        normalize_native_candles([wallex(start)], venue="wallex",
                                 market="spot", as_of=AS_OF)


def test_explicit_false_closed_flag_is_respected():
    start = AS_OF - timedelta(minutes=3)
    with pytest.raises(ValueError, match="no_fully_closed_candles"):
        normalize_native_candles([wallex(start, is_closed=False)], venue="wallex",
                                 market="spot", as_of=AS_OF)


def test_duplicate_opens_fail_closed():
    start = AS_OF - timedelta(minutes=5)
    with pytest.raises(ValueError, match="duplicate_candle_open_time"):
        normalize_native_candles([wallex(start), wallex(start)], venue="wallex",
                                 market="spot", as_of=AS_OF)


def test_gaps_are_reported_not_synthesized():
    start = AS_OF - timedelta(minutes=8)
    batch = normalize_native_candles(
        [wallex(start), wallex(start + timedelta(minutes=2))],
        venue="wallex", market="spot", as_of=AS_OF,
    )
    assert len(batch.gaps) == 1
    assert batch.gaps[0].expected_start == start + timedelta(minutes=1)


def test_mixed_symbols_rejected():
    start = AS_OF - timedelta(minutes=4)
    other = wallex(start + timedelta(minutes=1))
    other.symbol = "ETHUSDT"
    with pytest.raises(ValueError, match="mixed_symbol_or_timeframe"):
        normalize_native_candles([wallex(start), other], venue="wallex",
                                 market="spot", as_of=AS_OF)


def test_invalid_ohlc_rejected():
    start = AS_OF - timedelta(minutes=3)
    bad = wallex(start, close="105")
    with pytest.raises(ValueError, match="invalid_ohlc_range"):
        normalize_native_candles([bad], venue="wallex", market="spot", as_of=AS_OF)



def test_bridge_output_feeds_existing_ema_consumer():
    start = AS_OF - timedelta(minutes=3)
    batch = normalize_native_candles([wallex(start)], venue="wallex",
                                     market="spot", as_of=AS_OF)
    snapshots = EMACalculator(period=1).calculate(to_feature_candles(batch))
    assert len(snapshots) == 1
    assert snapshots[0].symbol == "BTCUSDT"
    assert snapshots[0].value == 100.2


def test_binance_market_identity_must_match_requested_market():
    start = AS_OF - timedelta(minutes=3)
    candle = BinanceLike(
        "usdm_futures", "BTCUSDT", "1m", int(start.timestamp() * 1000),
        int((start + timedelta(minutes=1)).timestamp() * 1000) - 1,
        Decimal("100"), Decimal("101"), Decimal("99"),
        Decimal("100.5"), Decimal("5.25"),
    )
    with pytest.raises(ValueError, match="mixed_market"):
        normalize_native_candles([candle], venue="binance",
                                 market="spot", as_of=AS_OF)



def test_binance_inclusive_close_time_is_canonicalized_to_exclusive_end():
    start = AS_OF - timedelta(minutes=3)
    candle = BinanceLike(
        "spot", "BTCUSDT", "1m", int(start.timestamp() * 1000),
        int((start + timedelta(minutes=1)).timestamp() * 1000) - 1,
        Decimal("100"), Decimal("101"), Decimal("99"),
        Decimal("100.5"), Decimal("5.25"),
    )
    batch = normalize_native_candles([candle], venue="binance",
                                     market="spot", as_of=AS_OF)
    assert batch.candles[0].end - batch.candles[0].start == timedelta(minutes=1)


def test_inconsistent_candle_duration_is_rejected():
    start = AS_OF - timedelta(minutes=3)
    candle = wallex(start)
    candle.close_time = start + timedelta(seconds=59)
    with pytest.raises(ValueError, match="candle_duration_mismatch"):
        normalize_native_candles([candle], venue="wallex",
                                 market="spot", as_of=AS_OF)
