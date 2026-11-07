import json
import os
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import web.dashboard as dashboard
from web.dashboard import Handler
from test_dashboard_routes_v1 import sample_batch


class DashboardOrdersPlacedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        with dashboard._CACHE_LOCK:
            dashboard._CACHE.clear()

    def test_health_success_and_failure_explicitly_report_no_orders(self):
        with patch("web.dashboard._get_batch", return_value=(sample_batch(), SimpleNamespace())):
            with urlopen(self.base + "/healthz") as response:
                self.assertFalse(json.loads(response.read())["orders_placed"])
        with patch("web.dashboard._get_batch", side_effect=TimeoutError("feed unavailable")):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + "/healthz")
        self.assertFalse(json.loads(error.exception.read())["orders_placed"])

    def test_candles_and_signal_failure_explicitly_report_no_orders(self):
        batch = sample_batch()
        features = SimpleNamespace(decision_ready=False, reason="INSUFFICIENT_CLOSED_CANDLES")
        with patch("web.dashboard._SOURCE.fetch", return_value=batch), patch("web.dashboard._FEATURES.build", return_value=features):
            with urlopen(self.base + "/api/candles?symbol=BTCUSDT&interval=15m") as response:
                self.assertFalse(json.loads(response.read())["orders_placed"])
        with patch("web.dashboard._get_batch", side_effect=TimeoutError("feed unavailable")):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + "/api/signal?symbol=BTCUSDT&interval=15m")
        self.assertFalse(json.loads(error.exception.read())["orders_placed"])

    def test_journal_and_order_rejection_explicitly_report_no_orders(self):
        with tempfile.TemporaryDirectory() as tempdir:
            missing = os.path.join(tempdir, "not-created.jsonl")
            with patch.dict(os.environ, {"HES_TRADE_JOURNAL_PATH": missing}):
                with urlopen(self.base + "/api/journal?limit=50") as response:
                    self.assertFalse(json.loads(response.read())["orders_placed"])
        request = Request(self.base + "/api/order", data=b"{}", method="POST")
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 405)
        self.assertFalse(json.loads(error.exception.read())["orders_placed"])


if __name__ == "__main__":
    unittest.main()
