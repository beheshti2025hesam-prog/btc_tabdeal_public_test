#!/usr/bin/env python3
"""Read-only market snapshot from the validated global candle feed; never trades."""
import json, math, time, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forward.global_market_data_reader_v1 import load_market_input

def ema(vals, period):
    alpha=2/(period+1); out=[]; cur=vals[0]
    for v in vals:
        cur=alpha*v+(1-alpha)*cur; out.append(cur)
    return out

def rsi(vals, period=14):
    if len(vals)<=period: return None
    gains=[]; losses=[]
    for i in range(1,len(vals)):
        d=vals[i]-vals[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains[:period])/period; al=sum(losses[:period])/period
    for i in range(period,len(gains)):
        ag=(ag*(period-1)+gains[i])/period; al=(al*(period-1)+losses[i])/period
    return 100 if al==0 else 100-100/(1+ag/al)

def mfi(rows, period=14):
    if len(rows)<=period: return None
    tp=[(float(r["high"])+float(r["low"])+float(r["close"]))/3 for r in rows]
    pos=neg=0.0
    for i in range(len(tp)-period,len(tp)):
        flow=tp[i]*float(rows[i]["volume"])
        if tp[i]>tp[i-1]: pos+=flow
        elif tp[i]<tp[i-1]: neg+=flow
    return 100 if neg==0 else 100-100/(1+pos/neg)

def snapshot(tf, rows):
    c=[float(r["close"]) for r in rows]
    e50=ema(c,50)[-1]; e200=ema(c,200)[-1]
    recent=rows[-20:]
    high20=max(float(r["high"]) for r in recent[:-1])
    low20=min(float(r["low"]) for r in recent[:-1])
    last=rows[-1]
    typ=[(float(r["high"])+float(r["low"])+float(r["close"]))/3 for r in recent]
    vols=[float(r["volume"]) for r in recent]
    vwap=sum(t*v for t,v in zip(typ,vols))/sum(vols) if sum(vols)>0 else None
    tr=[]
    for i in range(1,len(rows)):
        h=float(rows[i]["high"]); l=float(rows[i]["low"]); pc=float(rows[i-1]["close"])
        tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    atr=sum(tr[-14:])/min(14,len(tr))
    close=c[-1]
    return {
      "timeframe":tf,"bars":len(rows),"last_closed_open_time":last["open_time"],
      "last_closed_at_utc":datetime.fromtimestamp(int(last["close_time"]),timezone.utc).isoformat(),
      "close":close,"ema50":round(e50,4),"ema200":round(e200,4),
      "ema50_vs_ema200":"BULLISH" if e50>e200 else "BEARISH" if e50<e200 else "FLAT",
      "close_vs_ema50":"ABOVE" if close>e50 else "BELOW",
      "rsi14":round(rsi(c),2) if rsi(c) is not None else None,
      "mfi14":round(mfi(rows),2) if mfi(rows) is not None else None,
      "atr14":round(atr,4),"vwap20":round(vwap,4) if vwap is not None else None,
      "close_vs_vwap20":"ABOVE" if vwap and close>vwap else "BELOW" if vwap else "UNAVAILABLE",
      "prior20_high":high20,"prior20_low":low20,
      "close_breakout20":"UP" if close>high20 else "DOWN" if close<low20 else "NONE",
      "volume_last":float(last["volume"]),
      "candle_closed":last["closed"]
    }

def main():
    data=load_market_input(root="/opt/hes-trade-agent")
    out={
      "schema":"hes_gateio_market_snapshot_v1",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "source":data["source"],"symbol":data["symbol"],
      "timeframes":{tf:snapshot(tf,rows) for tf,rows in data["timeframes"].items()},
      "decision":"NO_TRADE",
      "decision_reason":"READ_ONLY_SNAPSHOT_ONLY; ADX, confirmed structure/sweep, strategy policy, and execution-grade risk validation are not yet implemented in this report. No live order is permitted."
    }
    p=Path("/opt/hes-trade-agent/data/forward/gateio_market_snapshot_v1.json")
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
