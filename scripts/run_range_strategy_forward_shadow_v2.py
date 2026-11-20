"""Read-only replay of recent VPS Gate.io forward candles for Range v2."""
from __future__ import annotations
import bisect, hashlib, json, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from forward.range_strategy_engine_v2 import CostModel,evaluate_range_strategy
from forward.universal_indicator_engine_v1 import OHLCVBar

DATA=Path("/opt/hes-trade-agent/data/forward")
FILES={"15m":DATA/"global_market_candles_v1.jsonl","1m":DATA/"global_market_candles_1m_v1.jsonl",
       "1h":DATA/"global_market_candles_1h_v1.jsonl","4h":DATA/"global_market_candles_4h_v1.jsonl"}
SECONDS={"15m":900,"1m":60,"1h":3600,"4h":14400}
COSTS=(5,10,15,30)


def load(tf,path):
    raw=path.read_bytes()
    rows=[json.loads(x) for x in raw.decode().splitlines() if x.strip()]
    bars=[]
    for r in rows:
        if r.get("schema")!="hes_global_candle_v1" or r.get("source")!="gateio_public_spot" or r.get("symbol")!="BTC_USDT" or r.get("timeframe")!=tf:
            raise ValueError("NONCANONICAL_ROW:"+tf)
        if r.get("closed") is not True: continue
        if int(r["close_time"]) != int(r["open_time"])+SECONDS[tf]:
            raise ValueError("CANDLE_CLOSE_TIME_MISMATCH:"+tf)
        bars.append(OHLCVBar(int(r["open_time"]),float(r["open"]),float(r["high"]),float(r["low"]),
            float(r["close"]),float(r["volume"]),float(r["quote_volume"]),True))
    bars.sort(key=lambda b:b.timestamp)
    if len({b.timestamp for b in bars})!=len(bars): raise ValueError("DUPLICATE_CANDLE:"+tf)
    if any(bars[i+1].timestamp-bars[i].timestamp!=SECONDS[tf] for i in range(len(bars)-1)):
        raise ValueError("CANDLE_GAP:"+tf)
    return bars,hashlib.sha256(raw).hexdigest()


def main():
    loaded={}; hashes={}
    for tf,path in FILES.items():
        loaded[tf],hashes[tf]=load(tf,path)
    b15,b1,bh1,bh4=loaded["15m"],loaded["1m"],loaded["1h"],loaded["4h"]
    h1close=[b.timestamp+3600 for b in bh1]
    h4close=[b.timestamp+14400 for b in bh4]
    m1opens=[b.timestamp for b in b1]
    costs={str(x):{"raw_candidates":0,"cost_pass":0,"cost_reject":0,"one_minute_window_complete":0,
        "one_minute_window_missing":0} for x in COSTS}
    rejects=Counter()
    sweep_prefilter=0
    for i in range(219,len(b15)):
        bar=b15[i]
        observed_epoch=bar.timestamp+900
        n1=bisect.bisect_right(h1close,observed_epoch)
        n4=bisect.bisect_right(h4close,observed_epoch)
        if n1<220 or n4<220: continue
        w15=b15[max(0,i-239):i+1]
        w1=bh1[max(0,n1-240):n1]
        w4=bh4[max(0,n4-240):n4]
        observed=datetime.fromtimestamp(observed_epoch,tz=timezone.utc)
        # Evaluate once at zero cost; apply each fixed cost scenario below.
        c=evaluate_range_strategy(source="gateio_public_spot",symbol="BTC_USDT",timeframe="15m",
            observed_at=observed,bars_15m=w15,bars_1h=w1,bars_4h=w4,
            cost_model=CostModel("ZERO_COST_SCREEN",0.0,False))
        if c.state!="RESEARCH_CANDIDATE":
            if c.reason_codes: rejects.update(c.reason_codes)
            # Count sweep/reclaim prefilter independently from the final policy result.
            continue
        sweep_prefilter+=1
        for bps in COSTS:
            item=costs[str(bps)]
            item["raw_candidates"]+=1
            entry=c.entry_reference
            risk=abs(entry-c.stop_loss)
            reward=abs(c.take_profit-entry)
            cost=entry*(bps/10000.0)
            net_rr=(reward-cost)/(risk+cost)
            if reward<=cost or net_rr<1.20:
                item["cost_reject"]+=1
                continue
            item["cost_pass"]+=1
            # A full next-15m 1m window must contain exactly 15 contiguous closed candles.
            start=observed_epoch
            end=start+900
            left=bisect.bisect_left(m1opens,start)
            right=bisect.bisect_left(m1opens,end)
            window=b1[left:right]
            complete=(len(window)==15 and window[0].timestamp==start and
                all(window[j+1].timestamp-window[j].timestamp==60 for j in range(len(window)-1)))
            item["one_minute_window_complete" if complete else "one_minute_window_missing"]+=1
    report={"schema":"hes_range_strategy_v2_forward_shadow_report","policy_version":"2.0.0-research",
        "status":"RESEARCH_ONLY_NOT_ACTIVE","execution_enabled":False,"orders_placed":False,
        "source_files":{tf:{"path":str(FILES[tf]),"sha256":hashes[tf],"rows":len(loaded[tf]),
            "first_open_utc":datetime.fromtimestamp(loaded[tf][0].timestamp,tz=timezone.utc).isoformat(),
            "last_close_utc":datetime.fromtimestamp(loaded[tf][-1].timestamp+SECONDS[tf],tz=timezone.utc).isoformat()}
            for tf in FILES},
        "htf_source":"actual Gate.io 1h and 4h candle files; no resampling",
        "setup_source":"actual closed Gate.io 15m candle file",
        "precision_source":"actual closed Gate.io 1m candle file; window completeness only, no precision-entry approval",
        "candidate_setup_count":sweep_prefilter,"rejection_reason_counts":dict(rejects),
        "cost_scenarios":costs,
        "limitations":["This is a read-only historical replay of append-only VPS candle files, not a live paper order.",
            "A complete 1m window is only a data-availability check; the 1m precision-entry contract is not implemented here.",
            "Cost scenarios are assumptions, not verified fills or fee schedules.",
            "No candidate is an approval; all family candidates remain research-only."]}
    out=ROOT/"research/range_strategy_v2/forward_shadow_20261119.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps({"output":str(out),"rows":{tf:len(loaded[tf]) for tf in FILES},
        "candidate_setup_count":sweep_prefilter,"rejections":dict(rejects),"cost_scenarios":costs},indent=2))

if __name__=="__main__":main()
