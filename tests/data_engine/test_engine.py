"""
Tests for Mother Agent Data Engine.
"""

from datetime import datetime, timezone

from core.data_engine.engine import DataEngine


class FakeReader:
    """Simple in-memory reader for Engine tests."""

    def __init__(self, rows):
        self.rows = rows

    def read_all(self):
        yield from self.rows


def make_row(
    timestamp,
    sequence,
    price="100000",
    amount="0.001",
    side="buy",
    symbol="BTC_USDT",
):
    return {
        "symbol": symbol,
        "price": price,
        "amount": amount,
        "side": side,
        "updated": timestamp,
        "sequence": str(sequence),
    }


def test_engine_processes_valid_rows():
    rows = [
        make_row(
            "2026-09-20T10:00:01Z",
            2,
        ),
        make_row(
            "2026-09-20T10:00:00Z",
            1,
        ),
    ]

    engine = DataEngine(
        reader=FakeReader(rows)
    )

    result = engine.load()

    assert len(result) == 2
    assert all(
        trade.symbol == "BTC_USDT"
        for trade in result
    )


def test_engine_skips_invalid_rows():
    rows = [
        make_row(
            "2026-09-20T10:00:00Z",
            1,
        ),
        make_row(
            "2026-09-20T10:00:01Z",
            2,
            price="INVALID",
        ),
    ]

    engine = DataEngine(
        reader=FakeReader(rows)
    )

    result = engine.load()

    assert len(result) == 1
    assert result[0].sequence == 1


def test_engine_removes_duplicate_event_ids():
    rows = [
        make_row(
            "2026-09-20T10:00:00Z",
            1,
        ),
        make_row(
            "2026-09-20T10:00:00Z",
            1,
        ),
    ]

    engine = DataEngine(
        reader=FakeReader(rows)
    )

    result = engine.load()

    assert len(result) == 1
    assert result[0].sequence == 1


def test_engine_sorts_by_timestamp():
    rows = [
        make_row(
            "2026-09-20T10:00:03Z",
            3,
        ),
        make_row(
            "2026-09-20T10:00:01Z",
            1,
        ),
        make_row(
            "2026-09-20T10:00:02Z",
            2,
        ),
    ]

    engine = DataEngine(
        reader=FakeReader(rows)
    )

    result = engine.load()

    timestamps = [
        trade.timestamp
        for trade in result
    ]

    assert timestamps == sorted(timestamps)


def test_engine_does_not_depend_on_input_order():
    rows = [
        make_row(
            "2026-09-20T10:00:03Z",
            3,
        ),
        make_row(
            "2026-09-20T10:00:01Z",
            1,
        ),
        make_row(
            "2026-09-20T10:00:02Z",
            2,
        ),
    ]

    engine = DataEngine(
        reader=FakeReader(rows)
    )

    result = engine.load()

    assert [
        trade.sequence
        for trade in result
    ] == [1, 2, 3]


def test_engine_returns_empty_result_for_empty_input():
    engine = DataEngine(
        reader=FakeReader([])
    )

    result = engine.load()

    assert result == []


def test_engine_output_is_canonical_trade():
    rows = [
        make_row(
            "2026-09-20T10:00:00Z",
            123,
            price="100500.25",
            amount="0.0025",
            side="sell",
        )
    ]

    engine = DataEngine(
        reader=FakeReader(rows)
    )

    result = engine.load()

    trade = result[0]

    assert trade.event_id
    assert trade.source == "raw_csv"
    assert trade.exchange == "tabdeal"
    assert trade.symbol == "BTC_USDT"
    assert trade.price == 100500.25
    assert trade.quantity == 0.0025
    assert trade.side == "sell"
    assert trade.sequence == 123
    assert trade.timestamp == datetime(
        2026,
        9,
        20,
        10,
        0,
        0,
        tzinfo=timezone.utc,
    )
