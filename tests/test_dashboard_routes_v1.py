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


def sample_batch(*, gaps=(), interval="1m"):
    now_ms=int(time.time()*1000)
    interval_ms=dashboard.INTERVAL_MS[interval]
    open_ms=(now_ms//interval_ms-1)*interval_ms
    close_ms=open_ms+interval_ms-1
    fetched=now_ms
    candle=SimpleNamespace(
        venue="binance",product="spot",symbol="BTCUSDT",interval=interval,
        open_time_ms=open_ms,close_time_ms=close_ms,
        open=Decimal("100.00"),high=Decimal("102.00"),low=Decimal("99.00"),
        close=Decimal("101.00"),volume=Decimal("2.500"),quote_volume=Decimal("250.625"),
        trade_count=12,taker_buy_volume=Decimal("1.600"),
        taker_buy_quote_volume=Decimal("160.400"),closed=True,
    )
    return SimpleNamespace(
        venue="binance",product="spot",symbol="BTCUSDT",interval=interval,
        endpoint_kind="klines",fetched_at_ms=fetched,response_sha256="a"*64,
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
        self.assertIn("Signal Agent v1",page)
        self.assertIn("/api/signal?symbol=BTCUSDT&interval=15m",page)
        self.assertIn("signalReasons",page)
        self.assertIn("signalStrategyQuality",page)
        self.assertIn("signalStrategyQuorum",page)
        self.assertIn("HOLD / NO_TRADE_ONLY",page)
        self.assertIn(dashboard.CHART_ASSET_PATH,page)
        self.assertNotIn("unpkg.com",page)
        self.assertIn("https://www.tradingview.com/",page)
        self.assertIn("LightweightCharts.CandlestickSeries",page)
        self.assertIn("Binance Spot",page)
        self.assertNotIn("Yahoo",page)
        self.assertNotIn("<canvas id=\"chart\"",page)

    def test_pinned_chart_asset_is_served_locally_with_license_notice(self):
        with urlopen(self.base+dashboard.CHART_ASSET_PATH) as response:
            payload=response.read()
            self.assertEqual(response.status,200)
            self.assertEqual(response.headers.get_content_type(),"text/javascript")
            self.assertIn("script-src 'self' 'unsafe-inline'",response.headers.get("Content-Security-Policy",""))
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


    def test_signal_entrypoint_is_wired_and_fails_closed_without_strategy_evidence(self):
        batch = sample_batch(interval="15m")
        features = SimpleNamespace(
            decision_ready=True,
            reason="feature_quality_passed",
            quality=SimpleNamespace(passed=True),
        )
        with patch("web.dashboard._get_batch", return_value=(batch, features)) as get_batch:
            with urlopen(self.base + "/api/signal?symbol=BTCUSDT&interval=15m") as response:
                payload = json.loads(response.read())
        get_batch.assert_called_once_with("BTCUSDT", "15m")
        self.assertEqual(payload["agent_version"], "hes-signal-agent-v1")
        self.assertEqual(payload["decision"], "NO_TRADE")
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertFalse(payload["execution_enabled"])
        self.assertTrue(payload["feature_quality_passed"])
        self.assertEqual(payload["strategy_quality_state"], "UNKNOWN")
        self.assertEqual(payload["strategy_quality_passed_count"], 0)
        self.assertEqual(payload["strategy_quality_required_count"], 5)
        self.assertEqual(payload["strategy_policy_version"], "hes-strategy-policy-v1")
        self.assertIsNone(payload["strategy_evidence_sha256"])
        self.assertIn("SYMBOL_MAPPING_EVIDENCE_MISSING", payload["blocked_reasons"])
        self.assertIn("VALIDATED_STRUCTURE_PROVIDER_NOT_WIRED", payload["blocked_reasons"])
        self.assertIn("STRATEGY_QUALITY_PROVIDER_NOT_WIRED", payload["blocked_reasons"])
        self.assertIn("RISK_GEOMETRY_MISSING", payload["blocked_reasons"])

    def test_signal_endpoint_rejects_unapproved_scope_before_fetch(self):
        with patch("web.dashboard._get_batch") as get_batch:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + "/api/signal?symbol=ETHUSDT&interval=15m")
        self.assertEqual(error.exception.code, 400)
        get_batch.assert_not_called()

    def test_signal_input_failure_returns_no_trade_and_never_fabricates_signal(self):
        with patch("web.dashboard._get_batch", side_effect=TimeoutError()):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + "/api/signal?symbol=BTCUSDT&interval=15m")
        self.assertEqual(error.exception.code, 503)
        payload = json.loads(error.exception.read())
        self.assertEqual(payload["decision"], "NO_TRADE")
        self.assertTrue(payload["fail_closed"])
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



    def test_dashboard_main_starts_websocket_only_for_exact_opt_in_value(self):
        dashboard._STREAM_STATE.update(status="disabled", reason=None, last_event_ms=None)
        with patch.dict(os.environ, {"HES_BINANCE_STREAM_ENABLED": "1"}):
            with patch("web.dashboard.Thread") as worker_thread, \
                 patch("web.dashboard.ThreadingHTTPServer") as server_factory:
                server_factory.return_value.serve_forever.return_value = None
                dashboard.main()
        worker_thread.assert_called_once_with(
            target=dashboard._stream_worker,
            name="hes-binance-spot-kline",
            daemon=True,
        )
        worker_thread.return_value.start.assert_called_once_with()
        self.assertEqual(dashboard._STREAM_STATE["status"], "starting")


if __name__=="__main__":
    unittest.main()
