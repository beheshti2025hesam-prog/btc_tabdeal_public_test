import importlib.util, unittest, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
p = ROOT / 'forward/global_market_data_gateio_v1.py'
spec = importlib.util.spec_from_file_location('gatefeed', p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class GateFeedTests(unittest.TestCase):
 def test_normalize_closed_candle(self):
  x=m.normalize_row(['1000','2.4','12','13','10','11','1.2'],now=1900)
  self.assertEqual(x['open_time'],1000); self.assertEqual(x['open'],'11'); self.assertEqual(x['close'],'12'); self.assertTrue(x['closed'])
 def test_open_candle_not_closed(self):
  self.assertFalse(m.normalize_row(['1000','2','12','13','10','11','1'],now=1500)['closed'])
 def test_reject_bad_ohlc(self):
  with self.assertRaises(ValueError): m.normalize_row(['1000','2','12','11','10','11','1'],now=2000)
 def test_reject_short_row(self):
  with self.assertRaises(ValueError): m.normalize_row(['1000','2'],now=2000)
 def test_symbol_scope_can_be_explicitly_selected(self):
  original=m.SYMBOL
  try:
   m.SYMBOL="ETH_USDT"
   x=m.normalize_row(["1000","2.4","12","13","10","11","1.2"],now=1900)
   self.assertEqual(x["symbol"],"ETH_USDT")
   msg={"channel":"spot.candlesticks","event":"update","result":{"n":"15m_ETH_USDT","t":"1000","v":"2400","a":"0.03","c":"12","h":"13","l":"10","o":"11"}}
   self.assertEqual(m.normalize_ws_message(msg,now=1900)["symbol"],"ETH_USDT")
  finally:
   m.SYMBOL=original
 def test_ws_name_format_and_volume_fields(self):
  msg={'channel':'spot.candlesticks','event':'update','result':{'n':'15m_BTC_USDT','t':'1000','v':'2400','a':'0.03','c':'12','h':'13','l':'10','o':'11'}}
  self.assertIsNotNone(m.normalize_ws_message(msg,now=1900))
  c=m.normalize_ws_message(msg,now=1900)
  self.assertEqual(c['quote_volume'],'2400'); self.assertEqual(c['volume'],'0.03')
 def test_idempotent_append(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'candles.jsonl'
   c=m.normalize_row(['1000','2','12','13','10','11','1'],now=2000)
   self.assertEqual(m._append_new([c],-1,path),1000)
   self.assertEqual(m._append_new([c],1000,path),1000)
   self.assertEqual(len(path.read_text().splitlines()),1)
if __name__=='__main__': unittest.main()
