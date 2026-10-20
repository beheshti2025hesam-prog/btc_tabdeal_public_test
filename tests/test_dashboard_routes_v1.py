import json,unittest
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
   page=r.read().decode();self.assertEqual(r.status,200);self.assertIn("HES Trade Agent",page);self.assertIn("NO_TRADE_ONLY",page);self.assertIn("/api/candles",page)
 def test_health_no_trade_only(self):
  with urlopen(self.base+"/healthz") as r:data=json.loads(r.read())
  self.assertEqual(data["mode"],"NO_TRADE_ONLY");self.assertFalse(data["execution_enabled"])
 def test_order_route_does_not_exist(self):
  with self.assertRaises(HTTPError) as e:urlopen(self.base+"/api/order")
  self.assertEqual(e.exception.code,404)
 def test_post_rejected(self):
  with self.assertRaises(HTTPError) as e:urlopen(Request(self.base+"/api/candles",data=b"{}",method="POST"))
  self.assertEqual(e.exception.code,405)
