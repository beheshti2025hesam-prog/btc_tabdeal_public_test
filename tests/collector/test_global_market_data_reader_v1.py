import json, tempfile, unittest
from pathlib import Path
from forward.global_market_data_reader_v1 import read_closed_candles, MarketDataRejected
NL=chr(10)

class ReaderTests(unittest.TestCase):
 def make_file(self, root, tf="15m", count=3, start=9000, symbol="BTC_USDT"):
  secs={"15m":900,"1h":3600,"4h":14400}[tf]
  rel={"15m":"data/forward/global_market_candles_v1.jsonl","1h":"data/forward/global_market_candles_1h_v1.jsonl","4h":"data/forward/global_market_candles_4h_v1.jsonl"}[tf]
  if symbol != "BTC_USDT": rel=f"data/forward/global_market_candles_{symbol}_{tf}_v1.jsonl"
  p=Path(root)/rel; p.parent.mkdir(parents=True,exist_ok=True)
  rows=[]
  for i in range(count):
   ts=start+i*secs
   rows.append({"schema":"hes_global_candle_v1","quote_volume":"12","source":"gateio_public_spot","symbol":symbol,"timeframe":tf,"open_time":ts,"close_time":ts+secs,"open":"10","high":"12","low":"9","close":"11","volume":"1","closed":True,"observed_at":"2026-10-24T00:00:00+00:00"})
  p.write_text(NL.join(json.dumps(x) for x in rows)+NL)
  return p

 def test_accept_valid(self):
  with tempfile.TemporaryDirectory() as d:
   self.make_file(d,count=3,start=9000)
   self.assertEqual(len(read_closed_candles("15m",root=d,now=9000+3*900,min_bars=3)),3)

 def test_reader_uses_bounded_tail_without_truncating_history(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=5002,start=0)
   original_count=len(p.read_text().splitlines())
   rows=read_closed_candles("15m",root=d,now=5002*900,min_bars=200)
   self.assertEqual(len(rows),5000)
   self.assertEqual(rows[0]["open_time"],1800)
   self.assertEqual(rows[-1]["open_time"],5001*900)
   self.assertEqual(len(p.read_text().splitlines()),original_count)

 def test_accept_eth_and_sol_symbol_scopes(self):
  for symbol in ("ETH_USDT", "SOL_USDT"):
   with tempfile.TemporaryDirectory() as d:
    self.make_file(d,count=3,start=9000,symbol=symbol)
    self.assertEqual(len(read_closed_candles("15m",root=d,now=9000+3*900,min_bars=3,symbol=symbol)),3)

 def test_registry_scopes_match_reader_symbol_allowlist(self):
  registry=json.loads((Path(__file__).resolve().parents[2]/"config/gateio_spot_instruments_v1.json").read_text())
  self.assertEqual(registry["provider"],"gateio_public_spot")
  self.assertEqual({x["symbol"] for x in registry["instruments"]},{"BTC_USDT","ETH_USDT","SOL_USDT"})
  self.assertFalse(next(x for x in registry["instruments"] if x["symbol"]=="ETH_USDT")["analysis_enabled"])
  self.assertFalse(next(x for x in registry["instruments"] if x["symbol"]=="SOL_USDT")["analysis_enabled"])

 def test_gateio_feed_instances_share_one_systemd_template(self):
  root=Path(__file__).resolve().parents[2]
  template=(root/"deploy/systemd/hes-global-market-data-gateio@.service").read_text()
  self.assertIn("EnvironmentFile=/etc/hes-trade-agent/feeds/%i.env",template)
  for symbol in ("ETH_USDT","SOL_USDT"):
   for tf in ("15m","1h","4h"):
    instance=symbol.lower().replace("_","-")+"-"+tf
    env=(root/f"deploy/systemd/feeds/{instance}.env").read_text()
    self.assertIn(f"HES_GLOBAL_CANDLES_SYMBOL={symbol}",env)
    self.assertIn(f"HES_GLOBAL_CANDLES_INTERVAL={tf}",env)
    self.assertIn(f"global_market_candles_{symbol}_{tf}_v1.jsonl",env)

 def test_non_crypto_profiles_stay_disabled_without_provider(self):
  profiles=json.loads((Path(__file__).resolve().parents[2]/"config/market_asset_profiles_v1.json").read_text())
  for market in ("fx", "us_equities", "iran_equities", "commodities"):
   self.assertEqual(profiles["profiles"][market]["status"], "disabled_unqualified")
   self.assertIsNone(profiles["profiles"][market]["data_provider"])
   self.assertFalse(profiles["profiles"][market]["execution_enabled"])

 def test_reject_unsupported_symbol(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaisesRegex(MarketDataRejected,"UNSUPPORTED_SYMBOL"):
    read_closed_candles("15m",root=d,now=20000,min_bars=3,symbol="DOGE_USDT")

 def test_reject_gap(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=3,start=9000); rows=[json.loads(x) for x in p.read_text().splitlines()]; rows[2]["open_time"]+=900; rows[2]["close_time"]+=900; p.write_text(NL.join(json.dumps(x) for x in rows))
   with self.assertRaisesRegex(MarketDataRejected,"CANDLE_INTERVAL_GAP"): read_closed_candles("15m",root=d,now=20000,min_bars=3)

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

 def test_reject_missing_quote_volume(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=3,start=9000)
   rows=[json.loads(x) for x in p.read_text().splitlines()]
   rows[1].pop("quote_volume")
   p.write_text(NL.join(json.dumps(x) for x in rows)+NL)
   with self.assertRaisesRegex(MarketDataRejected,"CANDLE_QUOTE_VOLUME_INVALID"):
    read_closed_candles("15m",root=d,now=12000,min_bars=3)

 def test_reject_wrong_candle_schema(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=3,start=9000)
   rows=[json.loads(x) for x in p.read_text().splitlines()]
   rows[1]["schema"]="other"
   p.write_text(NL.join(json.dumps(x) for x in rows)+NL)
   with self.assertRaisesRegex(MarketDataRejected,"CANDLE_SCHEMA_INVALID"):
    read_closed_candles("15m",root=d,now=12000,min_bars=3)

 def test_reject_non_finite_quote_volume(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.make_file(d,count=3,start=9000); rows=[json.loads(x) for x in p.read_text().splitlines()]; rows[1]["quote_volume"]="NaN"; p.write_text(NL.join(json.dumps(x) for x in rows)+NL)
   with self.assertRaisesRegex(MarketDataRejected,"CANDLE_QUOTE_VOLUME_INVALID"): read_closed_candles("15m",root=d,now=12000,min_bars=3)

if __name__=="__main__": unittest.main()
