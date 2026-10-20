import json,unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import patch
from forward.global_market_data_v1 import Candle
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from web.dashboard import Handler
class DashboardRouteTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler);cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.base=f"http://127.0.0.1:{cls.server.server_port}"
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
 def test_dashboard_served(self):
  with urlopen(self.base+"/") as r:
   page=r.read().decode();self.assertEqual(r.status,200);self.assertIn("HES Trade Agent",page);self.assertIn("NO_TRADE_ONLY",page);self.assertIn("/api/candles",page);self.assertIn("lightweight-charts@5.0.8",page);self.assertIn("integrity=\"sha384-8J8e9bGIwf7e9BLO5rwf4zJwNRKcypGnvuGzORD/t4TrFA1gWbl3Hsi/RvyWwBKl\"",page);self.assertIn("LightweightCharts.CandlestickSeries",page);self.assertNotIn("<canvas id=\"chart\"",page)
 def test_health_no_trade_only(self):
  with urlopen(self.base+"/healthz") as r:data=json.loads(r.read())
  self.assertEqual(data["mode"],"NO_TRADE_ONLY");self.assertFalse(data["execution_enabled"])
 def test_order_route_does_not_exist(self):
  with self.assertRaises(HTTPError) as e:urlopen(self.base+"/api/order")
  self.assertEqual(e.exception.code,404)
 def test_post_rejected(self):
  with self.assertRaises(HTTPError) as e:urlopen(Request(self.base+"/api/candles",data=b"{}",method="POST"))
  self.assertEqual(e.exception.code,405)
 def test_candle_route_uses_interval_seconds_for_freshness(self):
  now=datetime.now(timezone.utc); candle=Candle("test_source","global_crypto_usd","BTC-USD","5m",now-timedelta(minutes=10),now-timedelta(minutes=5),Decimal("100"),Decimal("102"),Decimal("99"),Decimal("101"),Decimal("0"))
  with patch("web.dashboard.fetch_closed_klines",return_value=(candle,)) as fetch:
   with urlopen(self.base+"/api/candles?symbol=BTC-USD&interval=5m") as response:self.assertEqual(response.status,200)
  self.assertEqual(fetch.call_args.kwargs["max_latest_age"],timedelta(seconds=600))
