import json
import time
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

from web import dashboard


class DashboardFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        with dashboard._CACHE_LOCK:
            dashboard._CACHE.clear()

    def get_json(self, path):
        try:
            with urlopen(self.base_url + path, timeout=10) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_freshness_sla_matches_existing_integrity_and_soak_contract(self):
        self.assertEqual(
            dashboard.MAX_CANDLE_AGE_SECONDS,
            {"1m": 120, "15m": 1080, "1h": 3780, "4h": 14580},
        )

    def test_chart_route_fails_closed_on_stale_one_hour_batch(self):
        now_ms = int(time.time() * 1000)
        stale_batch = SimpleNamespace(
            candles=[SimpleNamespace(close_time_ms=now_ms - 5000 * 1000)],
            gaps=(),
        )
        with (
            patch.object(dashboard._SOURCE, "fetch", return_value=stale_batch) as fetch,
            patch.object(dashboard, "validate_native_batch"),
            patch.object(dashboard._FEATURES, "build") as build,
        ):
            status, payload = self.get_json("/api/candles?symbol=BTCUSDT&interval=1h")
        self.assertEqual(status, 503)
        self.assertTrue(payload["fail_closed"])
        self.assertEqual(payload["reason_code"], "latest_closed_candle_stale")
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["orders_placed"])
        fetch.assert_called_once()
        build.assert_not_called()

    def test_chart_route_fails_closed_on_gapped_batch_before_feature_build(self):
        now_ms = int(time.time() * 1000)
        gapped_batch = SimpleNamespace(
            candles=[SimpleNamespace(close_time_ms=now_ms - 30 * 1000)],
            gaps=[SimpleNamespace(expected_open_time_ms=1, next_observed_open_time_ms=120001, missing_intervals=1)],
        )
        with (
            patch.object(dashboard._SOURCE, "fetch", return_value=gapped_batch) as fetch,
            patch.object(dashboard, "validate_native_batch"),
            patch.object(dashboard._FEATURES, "build") as build,
        ):
            status, payload = self.get_json("/api/candles?symbol=BTCUSDT&interval=1h")
        self.assertEqual(status, 503)
        self.assertTrue(payload["fail_closed"])
        self.assertEqual(payload["reason_code"], "persisted_candle_gaps_present")
        fetch.assert_called_once()
        build.assert_not_called()

    def test_stale_cached_batch_is_not_served_from_cache(self):
        now_ms = int(time.time() * 1000)
        stale_batch = SimpleNamespace(
            candles=[SimpleNamespace(close_time_ms=now_ms - 5000 * 1000)],
            gaps=(),
        )
        with dashboard._CACHE_LOCK:
            dashboard._CACHE[("BTCUSDT", "1h")] = (stale_batch, object(), now_ms)
        with (
            patch.object(dashboard._SOURCE, "fetch", return_value=stale_batch) as fetch,
            patch.object(dashboard, "validate_native_batch"),
            patch.object(dashboard._FEATURES, "build"),
        ):
            status, payload = self.get_json("/api/candles?symbol=BTCUSDT&interval=1h")
        self.assertEqual(status, 503)
        self.assertEqual(payload["reason_code"], "latest_closed_candle_stale")
        fetch.assert_called_once()

    def test_precision_entry_blocks_stale_one_hour_context_before_engine(self):
        now_s = int(time.time())
        periods = {"4h": 14400, "1h": 3600, "15m": 900, "1m": 60}
        ages = {"4h": 5000, "1h": 5000, "15m": 500, "1m": 30}
        rows_by_tf = {}
        for tf, period in periods.items():
            latest_close = now_s - ages[tf]
            rows = []
            for index in range(240):
                close_time = latest_close - (239 - index) * period
                rows.append({
                    "open_time": close_time - period,
                    "close_time": close_time,
                    "open": "100.0",
                    "high": "101.0",
                    "low": "99.0",
                    "close": "100.5",
                    "volume": "10.0",
                    "quote_volume": "1000.0",
                })
            rows_by_tf[tf] = rows
        strategy = {
            "latest_gate_evidence": {
                "confirmation": {"state": "UNCONFIRMED"},
                "risk": {"state": "RISK_REJECTED"},
            },
            "paper_setup": {
                "validated": False,
                "direction": "NONE",
                "reason_code": "NO_VALIDATED_SETUP",
                "context": None,
            },
            "decision": "NO_TRADE",
            "execution_enabled": False,
            "orders_placed": False,
        }
        with (
            patch("forward.global_market_data_reader_v1.read_closed_candles",
                  side_effect=lambda timeframe, **kwargs: rows_by_tf[timeframe]),
            patch.object(dashboard, "read_strategy_v2_dashboard", return_value=strategy),
            patch("forward.precision_entry_engine_v1.evaluate_precision_entry") as evaluate,
        ):
            status, payload = self.get_json("/api/precision-entry")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("STALE_CANDLE_1H", payload["reason_codes"])
        self.assertEqual(payload["timeframes"]["1h"]["status"], "STALE")
        self.assertEqual(payload["timeframes"]["1h"]["max_age_seconds"], 3780)
        for timeframe in ("4h", "15m", "1m"):
            self.assertEqual(payload["timeframes"][timeframe]["status"], "VALIDATED")
        self.assertEqual(payload["entry_state"], "BLOCKED")
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["orders_placed"])
        evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
