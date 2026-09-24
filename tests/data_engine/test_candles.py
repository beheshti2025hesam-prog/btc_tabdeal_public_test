import unittest
from datetime import datetime, timezone

from core.data_engine.candles import TradeCandleAggregator
from core.data_engine.normalizer import RawDataNormalizer


def trade(sequence, second, price, amount):
    return RawDataNormalizer().normalize_row({
        "symbol": "BTC_USDT",
        "price": str(price),
        "amount": str(amount),
        "side": "buy",
        "updated": f"2026-09-24T00:00:{second:02d}Z",
        "sequence": str(sequence),
    })


class CandleAggregatorTests(unittest.TestCase):
    def test_builds_ohlcv_from_trades(self):
        trades = [
            trade(3, 30, 101, 0.3),
            trade(1, 5, 100, 0.2),
            trade(2, 10, 103, 0.1),
        ]
        candle = TradeCandleAggregator(60).aggregate(trades)[0]
        self.assertEqual(candle.open, 100)
        self.assertEqual(candle.high, 103)
        self.assertEqual(candle.low, 100)
        self.assertEqual(candle.close, 101)
        self.assertAlmostEqual(candle.volume, 0.6)
        self.assertEqual(candle.trade_count, 3)

    def test_separates_time_buckets(self):
        candles = TradeCandleAggregator(60).aggregate([
            trade(1, 1, 100, 1),
            RawDataNormalizer().normalize_row({
                "symbol": "BTC_USDT",
                "price": "110",
                "amount": "1",
                "side": "sell",
                "updated": "2026-09-24T00:01:01Z",
                "sequence": "2",
            }),
        ])
        self.assertEqual(len(candles), 2)
        self.assertEqual(
            [c.start for c in candles],
            [
                datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 9, 24, 0, 1, tzinfo=timezone.utc),
            ],
        )
