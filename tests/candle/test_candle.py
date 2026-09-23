from datetime import datetime, timezone

from core.models.candle import Candle


def test_candle_model_contract():
    candle = Candle(
        timestamp=datetime(2026, 9, 20, 17, 0, tzinfo=timezone.utc),
        timeframe="15m",
        symbol="BTC_USDT",
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=12.5,
        trade_count=3,
    )

    assert candle.timestamp.tzinfo is not None
    assert candle.timeframe == "15m"
    assert candle.symbol == "BTC_USDT"
    assert candle.open == 100.0
    assert candle.high == 105.0
    assert candle.low == 99.0
    assert candle.close == 103.0
    assert candle.volume == 12.5
    assert candle.trade_count == 3
