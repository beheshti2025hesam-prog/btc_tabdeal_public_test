from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json, unittest
from forward.global_market_data_v1 import MarketDataError,parse_closed_klines,fetch_closed_klines
NOW=datetime(2026,10,20,12,5,tzinfo=timezone.utc)
def row(start,close="101",high="102",low="99",volume="4.2500",seconds=60):
 ms=int(start.timestamp()*1000);return [ms,"100",high,low,close,volume,ms+seconds*1000-1,"x"]
class Response:
 status=200
 def __init__(self,payload):self.payload=payload
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self):return json.dumps(self.payload).encode()
class GlobalMarketDataTests(unittest.TestCase):
 def test_closed_candle_preserves_decimal_volume(self):
  bars=parse_closed_klines([row(NOW-timedelta(minutes=2))],symbol="BTCUSDT",interval="1m",as_of=NOW)
  self.assertEqual(bars[0].volume,Decimal("4.2500"));self.assertEqual(bars[0].source,"binance_public_market_data")
 def test_open_candle_rejected(self):
  with self.assertRaisesRegex(MarketDataError,"no_closed_candles"):parse_closed_klines([row(NOW-timedelta(seconds=30))],symbol="BTCUSDT",interval="1m",as_of=NOW)
 def test_stale_candle_rejected(self):
  with self.assertRaisesRegex(MarketDataError,"latest_closed_candle_stale"):parse_closed_klines([row(NOW-timedelta(minutes=8))],symbol="BTCUSDT",interval="1m",as_of=NOW,max_latest_age=timedelta(seconds=120))
 def test_duplicate_timestamp_rejected(self):
  r=row(NOW-timedelta(minutes=2))
  with self.assertRaisesRegex(MarketDataError,"duplicate_candle_open_time"):parse_closed_klines([r,r],symbol="BTCUSDT",interval="1m",as_of=NOW)
 def test_bad_ohlc_rejected(self):
  with self.assertRaisesRegex(MarketDataError,"invalid_ohlc_or_volume"):parse_closed_klines([row(NOW-timedelta(minutes=2),close="105")],symbol="BTCUSDT",interval="1m",as_of=NOW)
 def test_transport_failure_fails_closed(self):
  def fail(*args,**kwargs):raise TimeoutError("timeout")
  with self.assertRaisesRegex(MarketDataError,"market_data_unavailable"):fetch_closed_klines(as_of=NOW,opener=fail)
 def test_public_endpoint_has_no_credentials(self):
  seen={}
  def opener(request,timeout):
   seen["url"]=request.full_url;seen["headers"]=request.header_items();return Response([row(NOW-timedelta(minutes=2))])
  self.assertEqual(len(fetch_closed_klines(as_of=NOW,opener=opener)),1)
  self.assertIn("data-api.binance.vision",seen["url"]);self.assertNotIn("X-MBX-APIKEY",[k.upper() for k,_ in seen["headers"]])
