from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json,unittest
from forward.global_market_data_v1 import MarketDataError,parse_chart_payload,fetch_closed_klines
NOW=datetime(2026,10,20,12,5,tzinfo=timezone.utc)
def payload(stamps,opens=None,highs=None,lows=None,closes=None,volumes=None):
 n=len(stamps);opens=opens or [100]*n;highs=highs or [102]*n;lows=lows or [99]*n;closes=closes or [101]*n;volumes=volumes or ["4.2500"]*n
 return {"chart":{"result":[{"timestamp":stamps,"indicators":{"quote":[{"open":opens,"high":highs,"low":lows,"close":closes,"volume":volumes}]}}],"error":None}}
class Response:
 status=200
 def __init__(self,data):self.data=data
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self):return json.dumps(self.data).encode()
class GlobalMarketDataTests(unittest.TestCase):
 def test_closed_bar_and_volume_preserved(self):
  ts=int((NOW-timedelta(minutes=2)).timestamp());bars=parse_chart_payload(payload([ts]),symbol="BTC-USD",interval="1m",as_of=NOW)
  self.assertEqual(bars[0].volume,Decimal("4.2500"));self.assertEqual(bars[0].source,"yahoo_finance_public_chart_unverified");self.assertEqual(bars[0].market,"crypto_usd_reference_unverified")
 def test_zero_source_volume_is_preserved_without_inference(self):
  ts=int((NOW-timedelta(minutes=2)).timestamp());bars=parse_chart_payload(payload([ts],volumes=[0]),symbol="BTC-USD",interval="1m",as_of=NOW)
  self.assertEqual(bars[0].volume,Decimal("0"))
 def test_open_bar_excluded(self):
  ts=int((NOW-timedelta(seconds=30)).timestamp())
  with self.assertRaisesRegex(MarketDataError,"no_closed_candles"):parse_chart_payload(payload([ts]),symbol="BTC-USD",interval="1m",as_of=NOW)
 def test_stale_bar_rejected(self):
  ts=int((NOW-timedelta(minutes=8)).timestamp())
  with self.assertRaisesRegex(MarketDataError,"latest_closed_candle_stale"):parse_chart_payload(payload([ts]),symbol="BTC-USD",interval="1m",as_of=NOW,max_latest_age=timedelta(seconds=120))
 def test_duplicate_timestamp_rejected(self):
  ts=int((NOW-timedelta(minutes=2)).timestamp())
  with self.assertRaisesRegex(MarketDataError,"duplicate_candle_open_time"):parse_chart_payload(payload([ts,ts]),symbol="BTC-USD",interval="1m",as_of=NOW)
 def test_bad_ohlc_rejected(self):
  ts=int((NOW-timedelta(minutes=2)).timestamp())
  with self.assertRaisesRegex(MarketDataError,"invalid_ohlc_or_volume"):parse_chart_payload(payload([ts],closes=[105]),symbol="BTC-USD",interval="1m",as_of=NOW)
 def test_array_mismatch_rejected(self):
  with self.assertRaisesRegex(MarketDataError,"global_chart_array_length_mismatch"):parse_chart_payload(payload([1,2],closes=[1]),symbol="BTC-USD",interval="1m",as_of=NOW)
 def test_transport_failure_fails_closed(self):
  def fail(*args,**kwargs):raise TimeoutError("timeout")
  with self.assertRaisesRegex(MarketDataError,"market_data_unavailable"):fetch_closed_klines(as_of=NOW,opener=fail)
 def test_global_endpoint_no_credentials(self):
  seen={};ts=int((NOW-timedelta(minutes=2)).timestamp())
  def opener(request,timeout):seen["url"]=request.full_url;seen["headers"]=request.header_items();return Response(payload([ts]))
  bars=fetch_closed_klines(as_of=NOW,opener=opener)
  self.assertEqual(len(bars),1);self.assertIn("query2.finance.yahoo.com/v8/finance/chart/BTC-USD",seen["url"])
  self.assertNotIn("AUTHORIZATION",[k.upper() for k,_ in seen["headers"]])
