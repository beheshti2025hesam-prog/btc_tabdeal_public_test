import json
import unittest
from decimal import Decimal

from forward.native_futures_ohlcv import parse_klines


def row(open_ms=0, close_ms=59_999, *, o="100.10", h="101.20",
        low="99.90", c="100.50", volume="2.000", quote="200.50",
        count=3, taker="1.250", taker_quote="125.20"):
    return [open_ms, o, h, low, c, volume, close_ms, quote, count,
            taker, taker_quote, "0"]


class NativeFuturesKlineTests(unittest.TestCase):
    def test_preserves_decimal_precision_and_closed_state(self):
        raw = json.dumps([row()], separators=(",", ":")).encode()
        candle = parse_klines(raw, symbol="BTCUSDT", interval="1m",
                              now_ms=60_000)[0]
        self.assertEqual(candle.open, Decimal("100.10"))
        self.assertEqual(candle.volume, Decimal("2.000"))
        self.assertTrue(candle.is_closed)

    def test_open_candle_is_marked_not_dropped(self):
        raw = json.dumps([row()], separators=(",", ":")).encode()
        candle = parse_klines(raw, symbol="BTCUSDT", interval="1m",
                              now_ms=59_000)[0]
        self.assertFalse(candle.is_closed)

    def test_rejects_malformed_row(self):
        with self.assertRaisesRegex(ValueError, "12 fields"):
            parse_klines(b'[[1,2]]', symbol="BTCUSDT", interval="1m",
                         now_ms=100_000)

    def test_rejects_duplicate_open_time(self):
        raw = json.dumps([row(), row()], separators=(",", ":")).encode()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_klines(raw, symbol="BTCUSDT", interval="1m",
                         now_ms=100_000)

    def test_rejects_misaligned_timestamp(self):
        raw = json.dumps([row(open_ms=1, close_ms=60_000)],
                         separators=(",", ":")).encode()
        with self.assertRaisesRegex(ValueError, "misaligned"):
            parse_klines(raw, symbol="BTCUSDT", interval="1m",
                         now_ms=100_000)

    def test_rejects_inconsistent_ohlc(self):
        raw = json.dumps([row(o="105", h="101", low="99", c="100")],
                         separators=(",", ":")).encode()
        with self.assertRaisesRegex(ValueError, "OHLC"):
            parse_klines(raw, symbol="BTCUSDT", interval="1m",
                         now_ms=100_000)

    def test_rejects_invalid_interval(self):
        with self.assertRaisesRegex(ValueError, "unsupported interval"):
            parse_klines(b'[]', symbol="BTCUSDT", interval="2m",
                         now_ms=100_000)


if __name__ == "__main__":
    unittest.main()
