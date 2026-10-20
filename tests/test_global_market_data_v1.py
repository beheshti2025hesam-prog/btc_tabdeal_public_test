from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import unittest

from forward.global_market_data_v1 import (
    MarketDataError, fetch_closed_klines, parse_closed_klines,
)

UTC = timezone.utc
NOW = datetime(2026, 10, 20, 12, 5, tzinfo=UTC)


def kline(start, *, close="101", high="102", low="99", volume="4.2500", interval_ms=60_000):
    open_ms = int(start.timestamp() * 1000)
    return [open_ms, "100", high, low, close, volume, open_ms + interval_ms - 1,
            "425", 42, "2", "3", "0"]


class FakeResponse:
    status = 200
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps(self.payload).encode()


class GlobalMarketDataTests(unittest.TestCase):
    def test_closed_candle_parses_with_identity_and_decimal_precision(self):
        start = NOW - timedelta(minutes=2)
        result = parse_closed_klines([kline(start)], symbol="BTCUSDT", interval="1m", as_of=NOW)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].venue, "binance")
        self.assertEqual(result[0].market, "spot")
        self.assertEqual(result[0].volume, Decimal("4.2500"))
        self.assertEqual(result[0].close_time, start + timedelta(minutes=1))

    def test_open_candle_is_excluded(self):
        start = NOW - timedelta(seconds=30)
        with self.assertRaisesRegex(MarketDataError, "no_fully_closed_candles"):
            parse_closed_klines([kline(start)], symbol="BTCUSDT", interval="1m", as_of=NOW)

    def test_stale_latest_closed_candle_fails_closed(self):
        start = NOW - timedelta(minutes=8)
        with self.assertRaisesRegex(MarketDataError, "latest_closed_candle_stale"):
            parse_closed_klines([kline(start)], symbol="BTCUSDT", interval="1m",
                                as_of=NOW, max_latest_age=timedelta(seconds=120))

    def test_freshness_boundary_is_accepted(self):
        start = NOW - timedelta(minutes=3)
        result = parse_closed_klines([kline(start)], symbol="BTCUSDT", interval="1m",
                                     as_of=NOW, max_latest_age=timedelta(seconds=120))
        self.assertEqual(len(result), 1)

    def test_duplicate_timestamp_is_rejected(self):
        start = NOW - timedelta(minutes=4)
        with self.assertRaisesRegex(MarketDataError, "duplicate_candle_open_time"):
            parse_closed_klines([kline(start), kline(start)], symbol="BTCUSDT",
                                interval="1m", as_of=NOW)

    def test_nonchronological_timestamp_is_rejected(self):
        start = NOW - timedelta(minutes=5)
        with self.assertRaisesRegex(MarketDataError, "candles_not_strictly_chronological"):
            parse_closed_klines([kline(start + timedelta(minutes=1)), kline(start)],
                                symbol="BTCUSDT", interval="1m", as_of=NOW)

    def test_bad_ohlc_is_rejected(self):
        with self.assertRaisesRegex(MarketDataError, "invalid_ohlc_range"):
            parse_closed_klines([kline(NOW - timedelta(minutes=2), close="105")],
                                symbol="BTCUSDT", interval="1m", as_of=NOW)

    def test_malformed_payload_is_rejected(self):
        with self.assertRaisesRegex(MarketDataError, "malformed_kline_0"):
            parse_closed_klines([["bad"]], symbol="BTCUSDT", interval="1m", as_of=NOW)

    def test_transport_error_is_reported_without_retry_or_fallback(self):
        def broken_opener(*args, **kwargs):
            raise TimeoutError("simulated timeout")
        with self.assertRaisesRegex(MarketDataError, "market_data_transport_or_payload_error"):
            fetch_closed_klines(symbol="BTCUSDT", interval="1m", as_of=NOW, opener=broken_opener)

    def test_fetch_uses_public_endpoint_and_no_credentials(self):
        captured = {}
        def fake_opener(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["timeout"] = timeout
            start = NOW - timedelta(minutes=2)
            return FakeResponse([kline(start)])
        result = fetch_closed_klines(symbol="BTCUSDT", interval="1m", as_of=NOW,
                                     opener=fake_opener, max_latest_age=timedelta(seconds=120))
        self.assertEqual(len(result), 1)
        self.assertIn("data-api.binance.vision/api/v3/klines", captured["url"])
        self.assertNotIn("X-MBX-APIKEY", {k.upper(): v for k, v in captured["headers"].items()})

    def test_unsupported_interval_and_invalid_limit_fail_closed(self):
        with self.assertRaisesRegex(MarketDataError, "unsupported_interval"):
            fetch_closed_klines(symbol="BTCUSDT", interval="2m", as_of=NOW)
        with self.assertRaisesRegex(MarketDataError, "limit_out_of_range"):
            fetch_closed_klines(symbol="BTCUSDT", interval="1m", limit=1001, as_of=NOW)


    def test_global_source_candles_feed_existing_native_bridge_without_sequence(self):
        from forward.native_candle_bridge_v1 import normalize_native_candles, to_feature_candles

        start = NOW - timedelta(minutes=2)
        source_candles = parse_closed_klines(
            [kline(start)], symbol="BTCUSDT", interval="1m", as_of=NOW,
            max_latest_age=timedelta(seconds=120),
        )
        batch = normalize_native_candles(
            source_candles, venue="binance", market="spot", as_of=NOW,
        )
        self.assertEqual(batch.identity.venue, "binance")
        self.assertEqual(batch.identity.market, "spot")
        self.assertEqual(batch.identity.symbol, "BTCUSDT")
        self.assertEqual(batch.identity.timeframe_seconds, 60)
        self.assertEqual(len(batch.candles), 1)
        feature_candles = to_feature_candles(batch)
        self.assertEqual(feature_candles[0].symbol, "BTCUSDT")
        self.assertIsNone(feature_candles[0].trade_count)
        self.assertIsNone(feature_candles[0].volume)


if __name__ == "__main__":
    unittest.main()
