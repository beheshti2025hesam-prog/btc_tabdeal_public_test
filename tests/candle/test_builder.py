from datetime import datetime, timezone

from core.models.trade import CanonicalTrade


def make_trade(minute, second, price, quantity):
    return CanonicalTrade(
        event_id=f"evt-{minute}-{second}",
        source="websocket",
        exchange="test",
        symbol="BTC_USDT",
        price=price,
        quantity=quantity,
        side="Buy",
        timestamp=datetime(
            2026,
            9,
            20,
            17,
            minute,
            second,
            tzinfo=timezone.utc,
        ),
    )


def test_candle_builder_15m_ohlcv():
    trades = [
        make_trade(2, 10, 100.0, 1.0),
        make_trade(5, 20, 105.0, 2.0),
        make_trade(9, 30, 99.0, 1.5),
        make_trade(12, 40, 103.0, 3.0),
    ]

    from core.candle_builder import CandleBuilder

    builder = CandleBuilder(timeframe="15m")
    candles = builder.build(trades)

    assert len(candles) == 1

    candle = candles[0]

    assert candle.timestamp == datetime(
        2026, 9, 20, 17, 0, tzinfo=timezone.utc
    )
    assert candle.timeframe == "15m"
    assert candle.symbol == "BTC_USDT"
    assert candle.open == 100.0
    assert candle.high == 105.0
    assert candle.low == 99.0
    assert candle.close == 103.0
    assert candle.volume == 7.5
    assert candle.trade_count == 4


def test_candle_builder_does_not_depend_on_input_order():
    trades = [
        make_trade(12, 40, 103.0, 3.0),
        make_trade(2, 10, 100.0, 1.0),
        make_trade(9, 30, 99.0, 1.5),
        make_trade(5, 20, 105.0, 2.0),
    ]

    from core.candle_builder import CandleBuilder

    builder = CandleBuilder(timeframe="15m")
    candles = builder.build(trades)

    assert len(candles) == 1

    candle = candles[0]

    assert candle.open == 100.0
    assert candle.high == 105.0
    assert candle.low == 99.0
    assert candle.close == 103.0
    assert candle.volume == 7.5
    assert candle.trade_count == 4


def test_candle_builder_skips_empty_buckets():
    trades = [
        make_trade(2, 10, 100.0, 1.0),
        make_trade(12, 40, 103.0, 2.0),
        make_trade(30, 10, 110.0, 1.5),
    ]

    from core.candle_builder import CandleBuilder

    builder = CandleBuilder(timeframe="15m")
    candles = builder.build(trades)

    assert len(candles) == 2

    assert candles[0].timestamp == datetime(
        2026, 9, 20, 17, 0, tzinfo=timezone.utc
    )
    assert candles[1].timestamp == datetime(
        2026, 9, 20, 17, 30, tzinfo=timezone.utc
    )

    assert candles[0].volume == 3.0
    assert candles[0].trade_count == 2

    assert candles[1].volume == 1.5
    assert candles[1].trade_count == 1
