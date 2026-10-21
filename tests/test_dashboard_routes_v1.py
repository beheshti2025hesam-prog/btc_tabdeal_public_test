from __future__ import annotations

import json
import time
import unittest
from decimal import Decimal
from http.server import ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from web.dashboard import Handler


def sample_batch(*, age_ms=1_000, gaps=()):
    now_ms=int(time.time()*1000)
    open_ms=(now_ms//60_000-1)*60_000
    close_ms=open_ms+59_999
    fetched=now_ms
    candle=SimpleNamespace(
        venue="binance",product="spot",symbol="BTCUSDT",interval="1m",
        open_time_ms=open_ms,close_time_ms=close_ms,
        open=Decimal("100.00"),high=Decimal("102.00"),low=Decimal("99.00"),
        close=Decimal("101.00"),volume=Decimal("2.500"),quote_volume=Decimal("250.625"),
        trade_count=12,taker_buy_volume=Decimal("1.600"),
        taker_buy_quote_volume=Decimal("160.400"),closed=True,
    )
    if age_ms:
        # The fixture timestamp is intentionally moved back by whole minutes
        # only in stale-data tests; default remains a recently closed 1m bar.
        pass
    return SimpleNamespace(
        venue="binance",product="spot",symbol="BTCUSDT",interval="1m",
        endpoint_kind="klines",fetched_at_ms=fetched,response_sha256="a"*64,
        candles=(candle,),gaps=tuple(gaps),open_candles_excluded=1,
    )


class DashboardRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)

    def test_dashboard_uses_pinned_chart_library_and_native_source_label(self):
        with urlopen(self.base+"/") as response:
            page=response.read().decode()
        self.assertIn("HES Trade Agent",page)
        self.assertIn("HOLD / NO_TRADE_ONLY",page)
        self.assertIn("lightweight-charts@5.0.8",page)
        self.assertIn("LightweightCharts.CandlestickSeries",page)
        self.assertIn("Binance Spot",page)
        self.assertNotIn("Yahoo",page)
        self.assertNotIn("<canvas id=\"chart\"",page)

    def test_health_and_execution_boundary(self):
        with urlopen(self.base+"/healthz") as response:
            payload=json.loads(response.read())
        self.assertEqual(payload["mode"],"NO_TRADE_ONLY")
        self.assertFalse(payload["execution_enabled"])
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base+"/api/order")
        self.assertEqual(error.exception.code,404)
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.base+"/api/candles",data=b"{}",method="POST"))
        self.assertEqual(error.exception.code,405)

    def test_chart_and_feature_pipeline_receive_the_same_native_batch(self):
        batch=sample_batch()
        features=SimpleNamespace(decision_ready=False,reason="INSUFFICIENT_CLOSED_CANDLES")
        with patch("web.dashboard._SOURCE.fetch",return_value=batch) as fetch, \
             patch("web.dashboard._FEATURES.build",return_value=features) as build:
            with urlopen(self.base+"/api/candles?symbol=BTCUSDT&interval=1m") as response:
                payload=json.loads(response.read())
        fetch.assert_called_once_with(symbol="BTCUSDT",interval="1m",limit=240)
        build.assert_called_once_with(batch)
        self.assertEqual(payload["source"],"binance_native_ohlcv_v1")
        self.assertEqual(payload["response_sha256"],"a"*64)
        self.assertEqual(payload["candles"][0]["open"],"100.00")
        self.assertEqual(payload["candles"][0]["volume"],"2.500")
        self.assertFalse(payload["feature_ready"])
        self.assertFalse(payload["execution_enabled"])

    def test_unsupported_symbol_or_interval_fails_before_source_call(self):
        with patch("web.dashboard._SOURCE.fetch") as fetch:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base+"/api/candles?symbol=BTC-USD&interval=1m")
        self.assertEqual(error.exception.code,400)
        fetch.assert_not_called()

    def test_source_failure_fails_closed_without_fake_candles(self):
        with patch("web.dashboard._SOURCE.fetch",side_effect=TimeoutError()):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base+"/api/candles?symbol=BTCUSDT&interval=1m")
        self.assertEqual(error.exception.code,503)
        payload=json.loads(error.exception.read())
        self.assertTrue(payload["fail_closed"])
        self.assertFalse(payload["execution_enabled"])


if __name__=="__main__":
    unittest.main()
