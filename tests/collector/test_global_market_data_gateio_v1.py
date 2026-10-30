import importlib.util, unittest, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
p = ROOT / 'forward/global_market_data_gateio_v1.py'
spec = importlib.util.spec_from_file_location('gatefeed', p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
from forward import global_market_data_reader_v1 as reader

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
 def test_rest_backfill_repairs_a_historical_gap_in_sorted_order(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'candles.jsonl'
   a=m.normalize_row(['900','2','12','13','10','11','1'],now=2000)
   b=m.normalize_row(['2700','2','12','13','10','11','1'],now=4000)
   middle=m.normalize_row(['1800','2','12','13','10','11','1'],now=3000)
   self.assertEqual(m._append_new([a,b],-1,path),2700)
   self.assertEqual(m._append_new([middle],2700,path),2700)
   rows=[__import__('json').loads(x) for x in path.read_text().splitlines()]
   self.assertEqual([x['open_time'] for x in rows],[900,1800,2700])
   self.assertEqual(m._append_new([middle],2700,path),2700)
   self.assertEqual(len(path.read_text().splitlines()),3)

 def test_persisted_candle_requires_quote_volume_and_valid_ohlc(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'candles.jsonl'
   c=m.normalize_row(['900','2','12','13','10','11','1'],now=2000)
   c.pop('quote_volume')
   path.write_text(__import__('json').dumps(c)+'\\n')
   with self.assertRaisesRegex(ValueError,'payload invalid'):
    m._read_saved_candles(path)

 def test_duplicate_persisted_candle_identity_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'candles.jsonl'
   c=m.normalize_row(['900','2','12','13','10','11','1'],now=2000)
   line=__import__('json').dumps(c)
   path.write_text(line+'\n'+line+'\n')
   with self.assertRaisesRegex(ValueError,'order/duplicate'):
    m._read_saved_candles(path)

 def test_conflicting_same_candle_identity_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'candles.jsonl'
   original=m.normalize_row(['900','2','12','13','10','11','1'],now=2000)
   conflict=dict(original); conflict['close']='12.5'
   m._append_new([original],-1,path)
   with self.assertRaisesRegex(ValueError,'Conflicting candle identity'):
    m._append_new([conflict],900,path)
   self.assertEqual(len(path.read_text().splitlines()),1)

 def test_incoming_wrong_instrument_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'candles.jsonl'
   candle=m.normalize_row(['900','2','12','13','10','11','1'],now=2000)
   candle['symbol']='SOL_USDT'
   with self.assertRaisesRegex(ValueError,'identity mismatch'):
    m._append_new([candle],-1,path)

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
 def test_ws_rejects_interval_only_or_wrong_symbol_identity(self):
  base={'channel':'spot.candlesticks','event':'update','result':{'n':'15m','t':'1000','v':'2400','a':'0.03','c':'12','h':'13','l':'10','o':'11'}}
  self.assertIsNone(m.normalize_ws_message(base,now=1900))
  base['result']['n']='15m_SOL_USDT'
  self.assertIsNone(m.normalize_ws_message(base,now=1900))

 def test_reject_zero_price(self):
  with self.assertRaisesRegex(ValueError,'Negative timestamp, price, or volume'):
   m.normalize_row(['1000','2','12','13','0','11','1'],now=2000)

 def test_ws_name_format_and_volume_fields(self):
  msg={'channel':'spot.candlesticks','event':'update','result':{'n':'15m_BTC_USDT','t':'1000','v':'2400','a':'0.03','c':'12','h':'13','l':'10','o':'11'}}
  self.assertIsNotNone(m.normalize_ws_message(msg,now=1900))
  c=m.normalize_ws_message(msg,now=1900)
  self.assertEqual(c['quote_volume'],'2400'); self.assertEqual(c['volume'],'0.03')
 def test_collector_and_reader_share_the_same_live_window(self):
  self.assertEqual(m.LIVE_WINDOW_CANDLES,reader.LIVE_WINDOW_CANDLES)

 def test_live_merge_window_is_bounded_without_truncating_history(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'candles.jsonl'
   rows=[]
   for i in range(m.LIVE_WINDOW_CANDLES + 2):
    ts=i*900
    rows.append(m.normalize_row([str(ts),'2','12','13','10','11','1'],now=ts+900))
   m._append_new(rows,-1,path)
   self.assertEqual(len(path.read_text().splitlines()),m.LIVE_WINDOW_CANDLES+2)
   saved=m._read_saved_candles(path)
   self.assertEqual(len(saved),m.LIVE_WINDOW_CANDLES)
   self.assertEqual(min(saved),2*900)
   self.assertEqual(max(saved),(m.LIVE_WINDOW_CANDLES+1)*900)

 def test_missing_ranges_are_chunked_at_gate_1000_point_limit(self):
  saved={900:{}, 900 + 1002*900:{}}
  self.assertEqual(m._missing_candle_ranges(saved),[(1800,900+1000*900),(900+1001*900,900+1001*900)])

 def test_rest_identical_duplicate_candle_is_idempotent(self):
  raw=['900','2','12','13','10','11','1']
  class Response:
   def raise_for_status(self): pass
   def json(self): return [raw,raw]
  class Session:
   def get(self,url,params,timeout): return Response()
  rows=m.fetch_recent_closed(Session(),now=2000)
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['open_time'],900)

 def test_rest_conflicting_duplicate_candle_fails_closed(self):
  first=['900','2','12','13','10','11','1']
  conflict=['900','2','12.5','13','10','11','1']
  class Response:
   def raise_for_status(self): pass
   def json(self): return [first,conflict]
  class Session:
   def get(self,url,params,timeout): return Response()
  with self.assertRaisesRegex(ValueError,'Conflicting Gate REST candle identity'):
   m.fetch_recent_closed(Session(),now=2000)

 def test_fetch_closed_range_uses_from_to_without_limit(self):
  class Response:
   def raise_for_status(self): pass
   def json(self): return [['900','2','12','13','10','11','1'],['1800','2','12','13','10','11','1']]
  class Session:
   def get(self,url,params,timeout):
    self.params=params
    return Response()
  session=Session()
  rows=m.fetch_closed_range(session,900,1800,now=3000)
  self.assertEqual([x['open_time'] for x in rows],[900,1800])
  self.assertEqual(session.params,{'currency_pair':m.SYMBOL,'interval':m.INTERVAL,'from':900,'to':1800})
  self.assertNotIn('limit',session.params)

 def test_backfill_repairs_gap_older_than_recent_window(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'candles.jsonl'
   a=m.normalize_row(['900','2','12','13','10','11','1'],now=2000)
   b=m.normalize_row(['2700','2','12','13','10','11','1'],now=4000)
   m._append_new([a,b],-1,path)
   class Response:
    def raise_for_status(self): pass
    def json(self): return [['1800','2','12','13','10','11','1']]
   class Session:
    def get(self,url,params,timeout):
     self.params=params
     return Response()
   session=Session()
   self.assertEqual(m._backfill_missing_history(session,path),1)
   rows=[__import__('json').loads(x) for x in path.read_text().splitlines()]
   self.assertEqual([x['open_time'] for x in rows],[900,1800,2700])
   self.assertEqual(session.params['from'],1800)
   self.assertEqual(session.params['to'],1800)

 def test_idempotent_append(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'candles.jsonl'
   c=m.normalize_row(['900','2','12','13','10','11','1'],now=2000)
   self.assertEqual(m._append_new([c],-1,path),900)
   self.assertEqual(m._append_new([c],900,path),900)
   self.assertEqual(len(path.read_text().splitlines()),1)
if __name__=='__main__': unittest.main()
