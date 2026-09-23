from core.candle_builder import CandleBuilder
from core.data_engine.engine import DataEngine


def test_data_engine_to_candle_builder(monkeypatch):
    rows = [
        {
            "symbol": "BTC_USDT",
            "price": "100.0",
            "amount": "1.0",
            "side": "Buy",
            "updated": "2026-09-20T17:02:10.000Z",
            "sequence": "1",
        },
        {
            "symbol": "BTC_USDT",
            "price": "105.0",
            "amount": "2.0",
            "side": "Sell",
            "updated": "2026-09-20T17:05:20.000Z",
            "sequence": "2",
        },
        {
            "symbol": "BTC_USDT",
            "price": "99.0",
            "amount": "1.5",
            "side": "Buy",
            "updated": "2026-09-20T17:09:30.000Z",
            "sequence": "3",
        },
        {
            "symbol": "BTC_USDT",
            "price": "103.0",
            "amount": "3.0",
            "side": "Sell",
            "updated": "2026-09-20T17:12:40.000Z",
            "sequence": "4",
        },
    ]

    class FakeReader:
        def read_all(self):
            return rows

    engine = DataEngine(reader=FakeReader())
    trades = engine.load()

    candles = CandleBuilder(timeframe="15m").build(trades)

    assert len(trades) == 4
    assert len(candles) == 1

    candle = candles[0]

    assert candle.symbol == "BTC_USDT"
    assert candle.open == 100.0
    assert candle.high == 105.0
    assert candle.low == 99.0
    assert candle.close == 103.0
    assert candle.volume == 7.5
    assert candle.trade_count == 4
