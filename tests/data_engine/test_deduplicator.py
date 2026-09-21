"""
Tests for Mother Agent Trade Deduplicator.
"""

from datetime import datetime, timezone

from core.data_engine.deduplicator import TradeDeduplicator
from core.models.trade import CanonicalTrade


def make_trade(event_id, sequence=1):
    return CanonicalTrade(
        event_id=event_id,
        source="raw_csv",
        exchange="tabdeal",
        symbol="BTC_USDT",
        price=100000.0,
        quantity=0.001,
        side="buy",
        timestamp=datetime(
            2026,
            9,
            20,
            10,
            0,
            0,
            tzinfo=timezone.utc,
        ),
        sequence=sequence,
        ingested_at=None,
    )


def test_unique_trades_are_preserved():
    deduplicator = TradeDeduplicator()

    trades = [
        make_trade("event-1", 1),
        make_trade("event-2", 2),
        make_trade("event-3", 3),
    ]

    result = list(
        deduplicator.deduplicate(trades)
    )

    assert result == trades


def test_duplicate_event_id_is_removed():
    deduplicator = TradeDeduplicator()

    trade_1 = make_trade("event-1", 1)
    trade_2 = make_trade("event-1", 2)

    result = list(
        deduplicator.deduplicate(
            [trade_1, trade_2]
        )
    )

    assert result == [trade_1]


def test_first_occurrence_is_preserved():
    deduplicator = TradeDeduplicator()

    first_trade = make_trade("event-1", 100)
    duplicate_trade = make_trade("event-1", 200)

    result = list(
        deduplicator.deduplicate(
            [first_trade, duplicate_trade]
        )
    )

    assert result[0] is first_trade


def test_multiple_duplicates_are_removed():
    deduplicator = TradeDeduplicator()

    trade_1 = make_trade("event-1", 1)
    trade_2 = make_trade("event-2", 2)
    trade_3 = make_trade("event-1", 3)
    trade_4 = make_trade("event-2", 4)
    trade_5 = make_trade("event-3", 5)

    result = list(
        deduplicator.deduplicate(
            [
                trade_1,
                trade_2,
                trade_3,
                trade_4,
                trade_5,
            ]
        )
    )

    assert result == [
        trade_1,
        trade_2,
        trade_5,
    ]


def test_empty_input_returns_empty_result():
    deduplicator = TradeDeduplicator()

    result = list(
        deduplicator.deduplicate([])
    )

    assert result == []


def test_raw_trade_objects_are_not_modified():
    deduplicator = TradeDeduplicator()

    trade_1 = make_trade("event-1", 1)
    trade_2 = make_trade("event-1", 2)

    original_trade_1 = trade_1
    original_trade_2 = trade_2

    result = list(
        deduplicator.deduplicate(
            [trade_1, trade_2]
        )
    )

    assert trade_1 is original_trade_1
    assert trade_2 is original_trade_2
    assert result == [trade_1]
