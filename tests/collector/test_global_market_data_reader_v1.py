import json, tempfile, unittest
from pathlib import Path
from forward.global_market_data_reader_v1 import read_closed_candles, MarketDataRejected
NL=chr(10)

class ReaderTests(unittest.TestCase):
 def make_file(self, root, tf="15m", count=3, start=9000):
  secs={"15m":900,"1h":3600,"4h":14400}[tf]
  rel={"15m":"data/forward/global_market_candles_v1.jsonl","1h":"data/forward/global_market_candles_1h_v1.jsonl","4h":"data/forward/global_market_candles_4h_v1.jsonl"}[tf]
  p=Path(root)/rel; p.parent.mkdir(parents=True,exist_ok=True)
  rows=[]
  for i in range(count):
   ts=start+i*secs
   rows.append({"source":"gateio_public_spot","symbol":"BTC_USDT","timeframe":tf,"open_time":ts,"close_time":ts+secs,"open":"10","high":"12","low":"9","close":"11","volume":"1","closed":True,"observed_at":"2026-10-24T00:00:00+00:00"})
  p.write_text(NL.join(json.dumps(x) for x in rows)+NL)
  return p

 def test_accept_valid(self):
  with tempfile.TemporaryDirectory() as d:
   self.make_file(d,count=3,start=9000)
   self.assertEqual(len(read_closed_candles("15m",root=d,now=9000+3*900,min_bars=3)),3)

 def test_reject_gap(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=3,start=9000); rows=[json.loads(x) for x in p.read_text().splitlines()]; rows[2]["open_time"]+=900; rows[2]["close_time"]+=900; p.write_text(NL.join(json.dumps(x) for x in rows))
   with self.assertRaisesRegex(MarketDataRejected,"CANDLE_INTERVAL_GAP"): read_closed_candles("15m",root=d,now=20000,min_bars=3)

 def test_reader_uses_bounded_tail_without_truncating_history(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=5002,start=0)
   original_count=len(p.read_text().splitlines())
   rows=read_closed_candles("15m",root=d,now=5002*900,min_bars=200)
   self.assertEqual(len(rows),5000)
   self.assertEqual(rows[0]["open_time"],1800)
   self.assertEqual(rows[-1]["open_time"],5001*900)
   self.assertEqual(len(p.read_text().splitlines()),original_count)

 def test_reject_misaligned_candle_open_time(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=3,start=9000)
   rows=[json.loads(x) for x in p.read_text().splitlines()]
   rows[1]["open_time"]+=1
   rows[1]["close_time"]+=1
   p.write_text(NL.join(json.dumps(x) for x in rows)+NL)
   with self.assertRaisesRegex(MarketDataRejected,"CANDLE_TIMESTAMP_ALIGNMENT_INVALID"):
    read_closed_candles("15m",root=d,now=12000,min_bars=3)

 def test_reject_wrong_source(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=3,start=9000); rows=[json.loads(x) for x in p.read_text().splitlines()]; rows[0]["source"]="tabdeal"; p.write_text(NL.join(json.dumps(x) for x in rows))
   with self.assertRaisesRegex(MarketDataRejected,"SOURCE_IDENTITY_MISMATCH"): read_closed_candles("15m",root=d,now=12000,min_bars=3)

 def test_reject_stale(self):
  with tempfile.TemporaryDirectory() as d:
   self.make_file(d,count=3,start=9000)
   with self.assertRaisesRegex(MarketDataRejected,"CANDLE_FEED_STALE"): read_closed_candles("15m",root=d,now=50000,min_bars=3)

 def test_reject_non_finite_base_volume(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=3,start=9000); rows=[json.loads(x) for x in p.read_text().splitlines()]; rows[1]["volume"]="NaN"; p.write_text(NL.join(json.dumps(x) for x in rows)+NL)
   with self.assertRaisesRegex(MarketDataRejected,"CANDLE_NON_FINITE_VALUE"): read_closed_candles("15m",root=d,now=12000,min_bars=3)

 def test_reject_non_finite_quote_volume(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=3,start=9000); rows=[json.loads(x) for x in p.read_text().splitlines()]; rows[1]["quote_volume"]="NaN"; p.write_text(NL.join(json.dumps(x) for x in rows)+NL)
   with self.assertRaisesRegex(MarketDataRejected,"CANDLE_QUOTE_VOLUME_INVALID"): read_closed_candles("15m",root=d,now=12000,min_bars=3)

if __name__=="__main__": unittest.main()
