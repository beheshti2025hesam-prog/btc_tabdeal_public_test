from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import tempfile
import unittest
from decimal import Decimal
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import web.dashboard as dashboard
from forward.native_ohlcv_gateio_v1 import (
    GATEIO_SPOT_SYMBOL_MAP, gateio_spot_source_symbol, verify_gateio_spot_symbol_mapping,
)
from forward.confirmation_engine_v1 import ConfirmationCheck
from forward.risk_gate_v1 import RiskCheck
from forward.strategy_policy_v1 import REQUIRED_CHECKS, StrategyEvidenceCheckV1
from web.dashboard import Handler


def provenance_from_rows(rows_by_tf):
    return {
        "schema": "hes_market_data_batch_provenance_v1",
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "batch_limit": 240,
        "timeframes": {
            timeframe: {
                "input_batch_sha256": dashboard.canonical_market_batch_sha256(rows_by_tf[timeframe]),
                "candle_count": min(len(rows_by_tf[timeframe]), 240),
                "last_closed_candle_time": rows_by_tf[timeframe][-1]["close_time"],
            }
            for timeframe in ("15m", "1h", "4h")
        },
    }


def fake_native_batch(rows):
    candle = SimpleNamespace(close_time_ms=int(rows[-1]["close_time"]) * 1000)
    return SimpleNamespace(
        response_sha256=dashboard.canonical_market_batch_sha256(rows),
        candles=(candle,),
    )


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


    def test_gateio_spot_symbol_mapping_is_explicit_and_shared_with_adapter(self):
        self.assertEqual(gateio_spot_source_symbol("BTCUSDT"), "BTC_USDT")
        self.assertTrue(verify_gateio_spot_symbol_mapping("BTCUSDT", "BTC_USDT"))
        self.assertFalse(verify_gateio_spot_symbol_mapping("BTCUSDT", "BTCUSDT"))
        self.assertFalse(verify_gateio_spot_symbol_mapping("ETHUSDT", "BTC_USDT"))
        with self.assertRaises(ValueError):
            gateio_spot_source_symbol("UNKNOWN")
        with self.assertRaises(TypeError):
            GATEIO_SPOT_SYMBOL_MAP["BTCUSDT"] = "WRONG_PAIR"

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

    def test_news_radar_panel_is_read_only_and_not_a_market_data_source(self):
        with urlopen(self.base + "/") as response:
            page = response.read().decode()
        self.assertIn('id="newsRadarPanel"', page)
        self.assertIn("Gate.io remains the sole live market-data source", page)
        with urlopen(self.base + "/static/dashboard.js") as response:
            script = response.read().decode()
        self.assertIn("fetch('/api/news'", script)
        self.assertNotIn("fetch('/api/signal", script)

    def test_mother_panel_and_browser_poll_are_present(self):
        with urlopen(self.base + "/") as response:
            page = response.read().decode()
        self.assertIn('id="motherPanel"', page)
        self.assertIn("Mother Orchestrator · canonical V2 evidence chain", page)
        with urlopen(self.base + "/static/dashboard.js") as response:
            script = response.read().decode()
        self.assertIn("fetch('/api/mother'", script)
        self.assertIn("witness", script)

    def test_mother_endpoint_returns_independently_witnessed_observation(self):
        strategy_view = {"status": "VERIFIED"}
        payload = {
            "schema": "hes.mother_v2_dashboard_view.v1", "status": "BLOCKED_GATE",
            "decision": "NO_TRADE", "stages": [{"agent": "confirmation", "state": "UNCONFIRMED"}],
            "witness": {"verified": True}, "execution_authorized": False,
            "execution_enabled": False, "orders_placed": False,
        }
        current_provenance = {
            "schema": "hes_market_data_batch_provenance_v1", "source": "gateio_public_spot",
            "symbol": "BTC_USDT", "batch_limit": 240, "timeframes": {},
        }
        with patch.object(dashboard, "_current_chart_batch_provenance", return_value=current_provenance), \
             patch.object(dashboard, "read_strategy_v2_dashboard", return_value=strategy_view) as strategy, \
             patch.object(dashboard, "read_mother_v2_dashboard", return_value=payload) as mother:
            with urlopen(self.base + "/api/mother") as response:
                result = json.loads(response.read())
                self.assertEqual(response.status, 200)
        strategy.assert_called_once_with(current_market_data_provenance=current_provenance)
        mother.assert_called_once_with(strategy_view=strategy_view)
        self.assertTrue(result["witness"]["verified"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])

    def test_mother_endpoint_fails_closed_without_verified_evidence(self):
        current_provenance = {
            "schema": "hes_market_data_batch_provenance_v1", "source": "gateio_public_spot",
            "symbol": "BTC_USDT", "batch_limit": 240, "timeframes": {},
        }
        with patch.object(dashboard, "_current_chart_batch_provenance", return_value=current_provenance), \
             patch.object(dashboard, "read_strategy_v2_dashboard",
                          side_effect=dashboard.StrategyV2DashboardError("stale report")):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + "/api/mother")
        self.assertEqual(error.exception.code, 503)
        result = json.loads(error.exception.read())
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertFalse(result["witness"]["verified"])
        self.assertTrue(result["fail_closed"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])

    def test_news_radar_exposes_freshness_classification(self):
        from pathlib import Path
        root = Path(dashboard.__file__).resolve().parents[1]
        page = dashboard.HTML
        script = (root / "web" / "static" / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn('id="newsFreshness"', page)
        self.assertIn('id="newsSourceDetails"', page)
        self.assertIn("freshness('future')", script)
        self.assertIn("freshness_status", script)
        self.assertIn("newest_age_minutes", script)

    def test_news_endpoint_returns_verified_snapshot(self):
        snapshot = {
            "schema_version": "hes.news_monitor_snapshot.v1",
            "monitor": {"status": "OK", "last_poll_at": "2026-11-01T12:00:00Z",
                        "source_profile_status": "partial_official_macro_regulatory_central_bank_and_venue_announcements",
                        "source_health": [{"source_id": "fed_press_all", "source_scope": "international", "status": "ok_empty"}]},
            "brief": {"schema_version": "hes.news_brief.v1", "status": "no_relevant_news",
                      "headline": "No high-impact relevant item", "findings": [], "veto_flags": [],
                      "provenance": {"source_failures": []}},
        }
        with patch.object(dashboard._NEWS_MONITOR, "read_snapshot", return_value=snapshot):
            with urlopen(self.base + "/api/news") as response:
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
        self.assertEqual(payload["monitor"]["status"], "OK")
        self.assertEqual(payload["brief"]["schema_version"], "hes.news_brief.v1")

    def test_news_endpoint_fails_closed_for_stale_or_corrupt_snapshot(self):
        with patch.object(dashboard._NEWS_MONITOR, "read_snapshot", side_effect=ValueError("news monitor snapshot stale")):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + "/api/news")
        self.assertEqual(error.exception.code, 503)
        payload = json.loads(error.exception.read())
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertTrue(payload["fail_closed"])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["orders_placed"])

    def test_legacy_signal_route_is_retired_without_running_or_writing(self):
        with patch.object(dashboard, "_get_batch", side_effect=AssertionError("legacy route must not fetch")):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + "/api/signal?symbol=BTCUSDT&interval=15m")
        self.assertEqual(error.exception.code, 410)
        payload = json.loads(error.exception.read())
        self.assertEqual(payload["decision"], "NO_TRADE")
        self.assertTrue(payload["fail_closed"])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["orders_placed"])

    def test_health_and_execution_boundary(self):
        batch=sample_batch()
        with patch("web.dashboard._get_batch",return_value=(batch,SimpleNamespace())):
            with urlopen(self.base+"/healthz") as response:
                payload=json.loads(response.read())
        self.assertEqual(payload["mode"],"NO_TRADE_ONLY")
        self.assertEqual(payload["status"],"ok")
        self.assertEqual(payload["input_batch_sha256"],"a"*64)
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["execution_instrument_mapping_verified"])
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base+"/api/order")
        self.assertEqual(error.exception.code,404)
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.base+"/api/candles",data=b"{}",method="POST"))
        self.assertEqual(error.exception.code,405)

    def test_health_fails_closed_when_persisted_feed_is_unavailable(self):
        with patch("web.dashboard._get_batch",side_effect=TimeoutError("feed unavailable")):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base+"/healthz")
        self.assertEqual(error.exception.code,503)
        payload=json.loads(error.exception.read())
        self.assertEqual(payload["status"],"blocked")
        self.assertTrue(payload["fail_closed"])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["execution_instrument_mapping_verified"])

    def test_health_fails_closed_when_latest_candle_is_stale(self):
        batch=sample_batch()
        stale_candle=SimpleNamespace(**{**batch.candles[-1].__dict__,"close_time_ms":int(time.time()*1000)-7_200_000})
        stale_batch=SimpleNamespace(**{**batch.__dict__,"candles":(stale_candle,)})
        with patch("web.dashboard._get_batch",return_value=(stale_batch,SimpleNamespace())):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base+"/healthz")
        self.assertEqual(error.exception.code,503)
        payload=json.loads(error.exception.read())
        self.assertEqual(payload["reason"],"ValueError")
        self.assertTrue(payload["fail_closed"])

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


    def test_dashboard_main_starts_only_the_news_monitor_worker_by_default(self):
        dashboard._STREAM_STATE.update(status="disabled", reason=None, last_event_ms=None)
        with patch.dict(os.environ):
            os.environ.pop("HES_BINANCE_STREAM_ENABLED", None)
            with patch("web.dashboard.Thread") as worker_thread, \
                 patch("web.dashboard.ThreadingHTTPServer") as server_factory:
                server_factory.return_value.serve_forever.return_value = None
                dashboard.main()
        worker_thread.assert_called_once()
        self.assertEqual(worker_thread.call_args.kwargs["target"], dashboard._NEWS_MONITOR.run_forever)
        self.assertEqual(worker_thread.call_args.kwargs["name"], "hes-news-monitor")
        self.assertEqual(dashboard._STREAM_STATE["status"], "disabled")
        server_factory.return_value.serve_forever.assert_called_once_with()


    def test_dashboard_main_never_starts_legacy_websocket_for_nonexact_opt_in_values(self):
        for value in ("", "true", "yes", "2", " 1"):
            with self.subTest(value=value):
                dashboard._STREAM_STATE.update(status="disabled", reason=None, last_event_ms=None)
                with patch.dict(os.environ, {"HES_BINANCE_STREAM_ENABLED": value}):
                    with patch("web.dashboard.Thread") as worker_thread, \
                         patch("web.dashboard.ThreadingHTTPServer") as server_factory:
                        server_factory.return_value.serve_forever.return_value = None
                        dashboard.main()
                worker_thread.assert_called_once()
                self.assertEqual(worker_thread.call_args.kwargs["target"], dashboard._NEWS_MONITOR.run_forever)
                self.assertEqual(dashboard._STREAM_STATE["status"], "disabled")


    def test_dashboard_main_never_starts_legacy_binance_websocket_in_gateio_mode(self):
        dashboard._STREAM_STATE.update(status="disabled", reason=None, last_event_ms=None)
        with patch.dict(os.environ, {"HES_BINANCE_STREAM_ENABLED": "1"}):
            with patch("web.dashboard.Thread") as worker_thread, \
                 patch("web.dashboard.ThreadingHTTPServer") as server_factory:
                server_factory.return_value.serve_forever.return_value = None
                dashboard.main()
        worker_thread.assert_called_once()
        self.assertEqual(worker_thread.call_args.kwargs["target"], dashboard._NEWS_MONITOR.run_forever)
        self.assertEqual(dashboard._STREAM_STATE["status"], "disabled")
        self.assertEqual(dashboard._STREAM_STATE["reason"], "gateio_stream_not_enabled")




    def test_journal_endpoint_fails_closed_when_canonical_journal_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tempdir:
            missing_path = os.path.join(tempdir, "not-created.jsonl")
            with patch.dict(os.environ, {"HES_TRADE_JOURNAL_PATH": missing_path}):
                with urlopen(self.base + "/api/journal?limit=50") as response:
                    payload = json.loads(response.read())
        self.assertEqual(payload["schema"], "hes.trade_journal_view.v1")
        self.assertEqual(payload["status"], "NOT_CONFIGURED")
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["events"], [])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["outcomes_inferred"])
        with urlopen(self.base + "/") as response:
            page = response.read().decode()
        self.assertIn("Trade Journal · Decision & Learning Evidence", page)
        with urlopen(self.base + "/static/dashboard.js") as response:
            script = response.read().decode()
        self.assertIn("refreshJournal", script)
        self.assertIn("j.decision_count", script)
        self.assertIn("total journal records", script)
        self.assertIn("td.textContent=value", script)


    def test_security_headers_and_read_only_methods(self):
        with urlopen(self.base+"/") as response:
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


    def test_dashboard_has_accessible_section_navigation_and_semantic_landmarks(self):
        with urlopen(self.base + "/") as response:
            page = response.read().decode("utf-8")
        self.assertIn('href="#main-content"', page)
        self.assertIn('<main id="main-content" tabindex="-1">', page)
        self.assertIn('<h1 class="brand">HES Trade Agent</h1>', page)
        self.assertIn('<nav class="section-nav" aria-label="Dashboard sections">', page)
        for section_id in ("marketPanel", "strategyV2Panel", "motherPanel",
                           "newsRadarPanel", "safetyPanel", "journalPanel"):
            with self.subTest(section_id=section_id):
                self.assertIn(f'id="{section_id}"', page)
                self.assertIn(f'href="#{section_id}"', page)
        self.assertIn('id="message" role="status" aria-live="polite"', page)
        self.assertIn('id="journalStatus" role="status" aria-live="polite"', page)
        self.assertIn('<caption class="sr-only">', page)
        with urlopen(self.base + "/static/dashboard.css") as response:
            css = response.read().decode("utf-8")
        self.assertIn(".skip-link:focus", css)
        self.assertIn(".section-nav", css)
        self.assertIn(":focus-visible", css)


    def test_market_data_root_uses_shared_mutable_store_not_release_directory(self):
        self.assertEqual(dashboard._market_data_root(), dashboard.PROJECT_ROOT)
        with patch.dict(os.environ, {"HES_GLOBAL_MARKET_DATA_ROOT": "/opt/hes-trade-agent"}):
            self.assertEqual(str(dashboard._market_data_root()), "/opt/hes-trade-agent")



    def test_dashboard_exposes_1m_chart_and_precision_panel_without_duplicate_sections(self):
        with urlopen(self.base + "/") as response:
            page = response.read().decode()
        self.assertIn('<option>1m</option>', page)
        self.assertLess(page.index('<option>15m</option>'), page.index('<option>1m</option>'))
        self.assertIn('id="precisionEntryPanel"', page)
        self.assertEqual(page.count('id="strategyV2Panel"'), 1)
        with urlopen(self.base + "/static/dashboard.js") as response:
            script = response.read().decode()
        self.assertIn("refreshPrecisionEntry", script)
        self.assertIn("fetch('/api/precision-entry'", script)

    def test_precision_entry_api_fails_closed_without_valid_15m_setup(self):
        rows = []
        now = int(time.time())
        start = (now // 60 - 201) * 60
        for i in range(200):
            ts = start + i * 60
            rows.append({
                "schema": "hes_global_candle_v1", "source": "gateio_public_spot",
                "symbol": "BTC_USDT", "timeframe": "1m", "open_time": ts,
                "close_time": ts + 60, "open": "100", "high": "101", "low": "99",
                "close": "100.5", "volume": "2", "quote_volume": "200", "closed": True,
            })
        strategy = {
            "decision": "NO_TRADE", "direction": "NONE",
            "latest_gate_evidence": {
                "confirmation": {"state": "UNCONFIRMED"},
                "risk": {"state": "RISK_REJECTED"},
            },
            "execution_enabled": False, "orders_placed": False,
        }
        rows_by_tf = {timeframe: rows for timeframe in ("15m", "1h", "4h")}
        current_provenance = provenance_from_rows(rows_by_tf)
        chart_1m = fake_native_batch(rows)
        with patch("forward.global_market_data_reader_v1.read_closed_candles", return_value=rows), \
             patch.object(dashboard, "_current_chart_batch_provenance", return_value=current_provenance), \
             patch.object(dashboard, "_get_batch", return_value=(chart_1m, None)), patch.object(
            dashboard, "read_strategy_v2_dashboard", return_value=strategy
        ):
            with urlopen(self.base + "/api/precision-entry") as response:
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("15M_SETUP_NOT_VALIDATED", payload["reason_codes"])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["orders_placed"])

    def test_precision_entry_api_requires_provenance_bound_15m_entry_context(self):
        rows = []
        now = int(time.time())
        start = (now // 60 - 201) * 60
        for i in range(200):
            ts = start + i * 60
            rows.append({
                "schema": "hes_global_candle_v1", "source": "gateio_public_spot",
                "symbol": "BTC_USDT", "timeframe": "1m", "open_time": ts,
                "close_time": ts + 60, "open": "100", "high": "101", "low": "99",
                "close": "100.5", "volume": "2", "quote_volume": "200", "closed": True,
            })
        strategy = {
            "decision": "LONG", "direction": "LONG",
            "latest_gate_evidence": {
                "confirmation": {"state": "CONFIRMED_LONG"},
                "risk": {"state": "RISK_APPROVED"},
            },
            "execution_enabled": False, "orders_placed": False,
        }
        rows_by_tf = {timeframe: rows for timeframe in ("15m", "1h", "4h")}
        current_provenance = provenance_from_rows(rows_by_tf)
        chart_1m = fake_native_batch(rows)
        with patch("forward.global_market_data_reader_v1.read_closed_candles", return_value=rows), \
             patch.object(dashboard, "_current_chart_batch_provenance", return_value=current_provenance), \
             patch.object(dashboard, "_get_batch", return_value=(chart_1m, None)), patch.object(
            dashboard, "read_strategy_v2_dashboard", return_value=strategy
        ):
            with urlopen(self.base + "/api/precision-entry") as response:
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["entry_context_status"], "MISSING")
        self.assertIn("15M_SETUP_NOT_VALIDATED", payload["reason_codes"])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["orders_placed"])

    def test_precision_entry_api_exposes_canonical_hashes_for_each_timeframe(self):
        now = int(time.time())
        rows_by_tf = {}
        for timeframe, seconds in (("4h", 14400), ("1h", 3600), ("15m", 900), ("1m", 60)):
            start = (now // seconds - 240) * seconds
            rows_by_tf[timeframe] = [
                {
                    "schema": "hes_global_candle_v1", "source": "gateio_public_spot",
                    "symbol": "BTC_USDT", "timeframe": timeframe,
                    "open_time": start + i * seconds,
                    "close_time": start + (i + 1) * seconds,
                    "open": "100", "high": "101", "low": "99",
                    "close": "100.5", "volume": "2", "quote_volume": "200", "closed": True,
                }
                for i in range(240)
            ]
        strategy = {
            "decision": "NO_TRADE", "direction": "NONE",
            "latest_gate_evidence": {
                "confirmation": {"state": "UNCONFIRMED"},
                "risk": {"state": "RISK_REJECTED"},
            },
            "execution_enabled": False, "orders_placed": False,
        }
        current_provenance = provenance_from_rows(rows_by_tf)
        chart_1m = fake_native_batch(rows_by_tf["1m"])
        with patch(
            "forward.global_market_data_reader_v1.read_closed_candles",
            side_effect=lambda timeframe, **kwargs: rows_by_tf[timeframe],
        ), patch.object(dashboard, "_current_chart_batch_provenance", return_value=current_provenance), \
             patch.object(dashboard, "_get_batch", return_value=(chart_1m, None)), \
             patch.object(dashboard, "read_strategy_v2_dashboard", return_value=strategy):
            with urlopen(self.base + "/api/precision-entry") as response:
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200)
        for timeframe in ("15m", "1m"):
            with self.subTest(timeframe=timeframe):
                entry = payload["timeframes"][timeframe]
                self.assertEqual(entry["status"], "VALIDATED")
                self.assertEqual(entry["source"], "gateio_public_spot")
                self.assertEqual(entry["source_reader"], "global_market_data_reader_v1")
                self.assertEqual(entry["symbol"], "BTC_USDT")
                self.assertEqual(entry["timeframe"], timeframe)
                self.assertEqual(entry["batch_candles"], 240)
                self.assertEqual(
                    entry["input_batch_sha256"],
                    dashboard.canonical_market_batch_sha256(rows_by_tf[timeframe]),
                )
        self.assertEqual(payload["setup_decision"], "NO_TRADE")
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["orders_placed"])

    def test_precision_entry_api_fails_closed_on_unavailable_market_data(self):
        with patch("forward.global_market_data_reader_v1.read_closed_candles",
                   side_effect=ValueError("stale 1m feed")):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + "/api/precision-entry")
        self.assertEqual(error.exception.code, 503)
        payload = json.loads(error.exception.read())
        self.assertTrue(payload["fail_closed"])
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["orders_placed"])

    def test_1m_chart_source_reuses_the_canonical_gateio_reader(self):
        now_ms = int(time.time() * 1000)
        last_open = (now_ms // 60_000 - 2) * 60
        rows = []
        for i in range(240):
            ts = last_open - (239 - i) * 60
            rows.append({
                "schema": "hes_global_candle_v1", "source": "gateio_public_spot",
                "symbol": "BTC_USDT", "timeframe": "1m", "open_time": ts,
                "close_time": ts + 60, "open": "100", "high": "101", "low": "99",
                "close": "100.5", "volume": "2", "quote_volume": "200", "closed": True,
            })
        market = {
            "source": "gateio_public_spot", "symbol": "BTC_USDT",
            "timeframes": {"15m": [], "1h": [], "4h": []},
        }
        with patch.object(dashboard, "load_market_input", return_value=market), patch(
            "forward.global_market_data_reader_v1.read_closed_candles", return_value=rows
        ) as reader:
            batch = dashboard._SOURCE.fetch(symbol="BTCUSDT", interval="1m", limit=240)
        reader.assert_called_once_with("1m", root=dashboard._market_data_root(), min_bars=1)
        self.assertEqual(batch.endpoint_kind, "global_market_data_reader_v1")
        self.assertEqual(batch.interval, "1m")
        self.assertEqual(len(batch.candles), 240)
        self.assertEqual(batch.venue, "gateio")

if __name__=="__main__":
    unittest.main()
