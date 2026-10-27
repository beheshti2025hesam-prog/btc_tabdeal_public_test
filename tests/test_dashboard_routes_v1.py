from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import unittest
from decimal import Decimal
from http.server import ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import web.dashboard as dashboard
from web.dashboard import Handler


def sample_batch(*, gaps=()):
    now_ms=int(time.time()*1000)
    interval_ms=900_000
    open_ms=(now_ms//interval_ms-1)*interval_ms
    close_ms=open_ms+interval_ms-1
    fetched=now_ms
    candle=SimpleNamespace(
        venue="gateio",product="spot",symbol="BTCUSDT",interval="15m",
        open_time_ms=open_ms,close_time_ms=close_ms,
        open=Decimal("100.00"),high=Decimal("102.00"),low=Decimal("99.00"),
        close=Decimal("101.00"),volume=Decimal("2.500"),quote_volume=Decimal("250.625"),
        trade_count=None,taker_buy_volume=None,
        taker_buy_quote_volume=None,closed=True,
    )
    return SimpleNamespace(
        venue="gateio",product="spot",symbol="BTCUSDT",interval="15m",
        endpoint_kind="global_market_data_reader_v1",fetched_at_ms=fetched,response_sha256="a"*64,
        candles=(candle,),gaps=tuple(gaps),open_candles_excluded=1,
    )


class DashboardRouteTests(unittest.TestCase):
    def setUp(self):
        with dashboard._CACHE_LOCK:
            dashboard._CACHE.clear()

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
        self.assertIn('<div class="panel chart-panel">',page)
        self.assertNotIn('class="panel" class="chart-panel"',page)
        self.assertIn(dashboard.CHART_ASSET_PATH,page)
        self.assertNotIn("unpkg.com",page)
        self.assertIn("https://www.tradingview.com/",page)
        self.assertIn('src="/static/dashboard.js"',page)
        with urlopen(self.base+"/static/dashboard.js") as response:
            self.assertEqual(response.headers.get_content_type(),"text/javascript")
            self.assertIn("LightweightCharts.CandlestickSeries",response.read().decode())
        with urlopen(self.base+"/static/dashboard.css") as response:
            self.assertEqual(response.headers.get_content_type(),"text/css")
            self.assertIn("#0b1220",response.read().decode())
        self.assertIn("Canonical persisted global feed",page)
        self.assertIn("same validated persisted Gate.io candles through the canonical global-market reader",page)
        self.assertIn("Base and quote volume fields follow Gate.io's documented candlestick schema",page)
        self.assertNotIn("its semantics are unverified",page)
        self.assertNotIn("Binance Spot is venue-specific",page)
        self.assertNotIn("Yahoo",page)
        self.assertNotIn("<canvas id=\"chart\"",page)

    def test_pinned_chart_asset_is_served_locally_with_license_notice(self):
        with urlopen(self.base+dashboard.CHART_ASSET_PATH) as response:
            payload=response.read()
            self.assertEqual(response.status,200)
            self.assertEqual(response.headers.get_content_type(),"text/javascript")
            self.assertIn("script-src 'self'",response.headers.get("Content-Security-Policy",""))
            self.assertNotIn("unsafe-inline",response.headers.get("Content-Security-Policy",""))
            self.assertNotIn("unpkg.com",response.headers.get("Content-Security-Policy",""))
        self.assertGreater(len(payload),100_000)
        digest=base64.b64encode(hashlib.sha384(payload).digest()).decode("ascii")
        self.assertEqual(digest,"8J8e9bGIwf7e9BLO5rwf4zJwNRKcypGnvuGzORD/t4TrFA1gWbl3Hsi/RvyWwBKl")
        notice=(dashboard.CHART_ASSET_FILE.parent/"NOTICE").read_text(encoding="utf-8")
        license_text=(dashboard.CHART_ASSET_FILE.parent/"LICENSE").read_text(encoding="utf-8")
        self.assertIn("TradingView",notice)
        self.assertIn("Apache License",license_text)

    def test_health_and_execution_boundary(self):
        with urlopen(self.base+"/healthz") as response:
            payload=json.loads(response.read())
        self.assertEqual(payload["mode"],"NO_TRADE_ONLY")
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["execution_instrument_mapping_verified"])
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
            with urlopen(self.base+"/api/candles?symbol=BTCUSDT&interval=15m") as response:
                payload=json.loads(response.read())
        fetch.assert_called_once_with(symbol="BTCUSDT",interval="15m",limit=240)
        build.assert_called_once_with(batch)
        self.assertEqual(payload["source"],"gateio_public_spot")
        self.assertEqual(payload["source_reader"],"global_market_data_reader_v1")
        self.assertEqual(payload["source_symbol"],"BTC_USDT")
        self.assertTrue(payload["symbol_mapping_verified"])
        self.assertFalse(payload["execution_instrument_mapping_verified"])
        self.assertFalse(payload["execution_instrument_mapping_verified"])
        self.assertEqual(payload["volume_semantics_contract"],"gateio_spot_candlestick_volume_v1")
        self.assertFalse(payload["trade_count_available"])
        self.assertFalse(payload["taker_buy_flow_available"])
        self.assertEqual(payload["input_batch_sha256"],"a"*64)
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
        with patch("web.dashboard._SOURCE.fetch") as fetch:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base+"/api/candles?symbol=BTCUSDT&interval=2h")
        self.assertEqual(error.exception.code,400)
        fetch.assert_not_called()

    def test_source_failure_fails_closed_without_fake_candles(self):
        with patch("web.dashboard._SOURCE.fetch",side_effect=TimeoutError()):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base+"/api/candles?symbol=BTCUSDT&interval=15m")
        self.assertEqual(error.exception.code,503)
        payload=json.loads(error.exception.read())
        self.assertTrue(payload["fail_closed"])
        self.assertFalse(payload["execution_enabled"])


    def test_dashboard_main_does_not_start_websocket_by_default(self):
        dashboard._STREAM_STATE.update(status="disabled", reason=None, last_event_ms=None)
        with patch.dict(os.environ):
            os.environ.pop("HES_BINANCE_STREAM_ENABLED", None)
            with patch("web.dashboard.Thread") as worker_thread, \
                 patch("web.dashboard.ThreadingHTTPServer") as server_factory:
                server_factory.return_value.serve_forever.return_value = None
                dashboard.main()
        worker_thread.assert_not_called()
        self.assertEqual(dashboard._STREAM_STATE["status"], "disabled")
        server_factory.return_value.serve_forever.assert_called_once_with()


    def test_dashboard_main_requires_exact_opt_in_value_for_websocket(self):
        for value in ("", "true", "yes", "2", " 1"):
            with self.subTest(value=value):
                dashboard._STREAM_STATE.update(status="disabled", reason=None, last_event_ms=None)
                with patch.dict(os.environ, {"HES_BINANCE_STREAM_ENABLED": value}):
                    with patch("web.dashboard.Thread") as worker_thread, \
                         patch("web.dashboard.ThreadingHTTPServer") as server_factory:
                        server_factory.return_value.serve_forever.return_value = None
                        dashboard.main()
                worker_thread.assert_not_called()
                self.assertEqual(dashboard._STREAM_STATE["status"], "disabled")



    def test_dashboard_main_never_starts_legacy_binance_websocket_in_gateio_mode(self):
        dashboard._STREAM_STATE.update(status="disabled", reason=None, last_event_ms=None)
        with patch.dict(os.environ, {"HES_BINANCE_STREAM_ENABLED": "1"}):
            with patch("web.dashboard.Thread") as worker_thread, \
                 patch("web.dashboard.ThreadingHTTPServer") as server_factory:
                server_factory.return_value.serve_forever.return_value = None
                dashboard.main()
        worker_thread.assert_not_called()
        self.assertEqual(dashboard._STREAM_STATE["status"], "disabled")
        self.assertEqual(dashboard._STREAM_STATE["reason"], "gateio_stream_not_enabled")



    def test_signal_agent_reuses_gateio_canonical_batch_and_fails_closed(self):
        batch = sample_batch()
        batch = SimpleNamespace(**{**batch.__dict__, "interval": "15m"})
        features = SimpleNamespace(
            decision_ready=False,
            reason="VOLUME_SEMANTICS_UNAPPROVED",
            quality=SimpleNamespace(passed=False),
        )
        with patch("web.dashboard._get_batch", return_value=(batch, features)) as get_batch:
            with urlopen(self.base + "/api/signal?symbol=BTCUSDT&interval=15m") as response:
                payload = json.loads(response.read())
        get_batch.assert_called_once_with("BTCUSDT", "15m")
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["decision"], "NO_TRADE")
        self.assertEqual(payload["source"], "gateio_public_spot")
        self.assertEqual(payload["source_reader"], "global_market_data_reader_v1")
        self.assertEqual(payload["input_batch_sha256"], "a" * 64)
        self.assertEqual(payload["response_sha256"], "a" * 64)
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["execution_instrument_mapping_verified"])
        self.assertEqual(payload["structure_direction"], "UNKNOWN")
        self.assertIn("SYMBOL_MAPPING_EVIDENCE_MISSING", payload["blocked_reasons"])
        self.assertIn("STRATEGY_QUALITY_PROVIDER_NOT_WIRED", payload["blocked_reasons"])

    def test_signal_agent_rejects_unsupported_scope_before_data_fetch(self):
        with patch("web.dashboard._get_batch") as get_batch:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + "/api/signal?symbol=ETHUSDT&interval=15m")
        self.assertEqual(error.exception.code, 400)
        get_batch.assert_not_called()

    def test_security_headers_and_read_only_methods(self):
        with urlopen(self.base+"/healthz") as response:
            headers=response.headers
            self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(headers.get("Referrer-Policy"), "no-referrer")
            self.assertIn("object-src 'none'", headers.get("Content-Security-Policy", ""))
            self.assertIn("base-uri 'self'", headers.get("Content-Security-Policy", ""))
            self.assertIn("form-action 'self'", headers.get("Content-Security-Policy", ""))
            self.assertIn("frame-ancestors 'none'", headers.get("Content-Security-Policy", ""))
            self.assertNotIn("unsafe-inline", headers.get("Content-Security-Policy", ""))
            self.assertEqual(headers.get("Permissions-Policy"), "camera=(), microphone=(), geolocation=()")
            self.assertEqual(headers.get("Cache-Control"), "no-store")
        for path in ("/api/order", "/api/orders", "/api/execute"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(self.base+path, data=b"{}", method="POST"))
                self.assertEqual(error.exception.code, 405)

if __name__=="__main__":
    unittest.main()
