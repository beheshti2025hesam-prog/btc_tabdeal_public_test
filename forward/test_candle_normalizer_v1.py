from datetime import datetime, timezone
from decimal import Decimal

import pytest

from candle_normalizer_v1 import TradeObservation, normalize_trades


def t(ts, seq, price="100", amount="1", symbol="BTC_USDT"):
    return TradeObservation(symbol, Decimal(price), Decimal(amount), "Buy",
                            datetime.fromisoformat(ts).replace(tzinfo=timezone.utc), seq)


def test_open_bucket_is_not_emitted():
    candles, gaps = normalize_trades(
        [t("2026-10-07T01:47:00", 1)],
        as_of=datetime(2026, 10, 7, 1, 59, 59, tzinfo=timezone.utc),
        expected_symbol="BTC_USDT",
    )
    assert candles == ()
    assert gaps == ()


def test_closed_bucket_is_emitted():
    candles, gaps = normalize_trades(
        [t("2026-10-07T01:01:00", 1, "100", "2"),
         t("2026-10-07T01:14:59", 2, "105", "3")],
        as_of=datetime(2026, 10, 7, 1, 15, tzinfo=timezone.utc),
        expected_symbol="BTC_USDT",
    )
    assert len(candles) == 1
    assert candles[0].open == Decimal("100")
    assert candles[0].high == Decimal("105")
    assert candles[0].close == Decimal("105")
    assert candles[0].volume == Decimal("5")
    assert gaps == ()


def test_missing_interval_is_explicit():
    candles, gaps = normalize_trades(
        [t("2026-10-07T01:01:00", 1), t("2026-10-07T01:31:00", 2)],
        as_of=datetime(2026, 10, 7, 1, 45, tzinfo=timezone.utc),
        expected_symbol="BTC_USDT",
    )
    assert len(candles) == 2
    assert len(gaps) == 1
    assert gaps[0].open_time == datetime(2026, 10, 7, 1, 15, tzinfo=timezone.utc)


def test_mixed_symbols_are_rejected():
    with pytest.raises(ValueError, match="mixed symbols"):
        normalize_trades(
            [t("2026-10-07T01:01:00", 1, symbol="BTC_USDT"),
             t("2026-10-07T01:02:00", 2, symbol="ETH_USDT")],
            as_of=datetime(2026, 10, 7, 1, 15, tzinfo=timezone.utc),
        )


def test_repeated_sequence_is_preserved_as_two_independent_trades():
    candles, gaps = normalize_trades(
        [t("2026-10-07T01:01:00", 1, "100"),
         t("2026-10-07T01:02:00", 1, "101")],
        as_of=datetime(2026, 10, 7, 1, 15, tzinfo=timezone.utc),
        expected_symbol="BTC_USDT",
    )
    assert len(candles) == 1
    assert candles[0].trade_count == 2
    assert candles[0].first_sequence == 1
    assert candles[0].last_sequence == 1
    assert gaps == ()


def test_missing_sequence_metadata_is_allowed():
    candles, gaps = normalize_trades(
        [t("2026-10-07T01:01:00", None, "100")],
        as_of=datetime(2026, 10, 7, 1, 15, tzinfo=timezone.utc),
        expected_symbol="BTC_USDT",
    )
    assert len(candles) == 1
    assert candles[0].trade_count == 1
    assert candles[0].first_sequence is None
    assert candles[0].last_sequence is None
    assert gaps == ()
