#!/usr/bin/env python3
"""Candidate C v1: deterministic evaluator specification + executable data pipeline.

Research-only. The script fails closed unless the frozen definition/snapshot lineage
is present and matches. No Rule-A evaluator is imported or reused.
"""
import csv, json, hashlib, math
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
DEF=ROOT/"evidence/candidate_c_definition_v1.json"
SNAP=ROOT/"evidence/candidate_c_fresh_snapshot_20261001.json"
RAW=ROOT/"data/trades.csv"

def sha256_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def load_json(p): return json.loads(p.read_text())

def true_range(prev_close, high, low):
    if prev_close is None: return high-low
    return max(high-low, abs(high-prev_close), abs(low-prev_close))

def ema(values, period):
    if not values: return []
    alpha=2/(period+1)
    out=[values[0]]
    for x in values[1:]: out.append(alpha*x+(1-alpha)*out[-1])
    return out

def atr(highs,lows,closes,period):
    trs=[]
    prev=None
    for h,l,c in zip(highs,lows,closes):
        trs.append(true_range(prev,h,l)); prev=c
    if not trs: return []
    out=[math.nan]*len(trs)
    if len(trs)>=period:
        out[period-1]=sum(trs[:period])/period
        for i in range(period,len(trs)):
            out[i]=(out[i-1]*(period-1)+trs[i])/period
    return out

def aggregate_1m(path):
    """Aggregate raw trades deterministically. Column aliases are accepted only
    when unambiguous; missing required fields fail closed."""
    required_sets=[("timestamp","price","quantity"),("time","price","quantity"),("timestamp","price","amount")]
    with path.open(newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f)
        fields=reader.fieldnames or []
        chosen=None
        for ts,p,q in required_sets:
            if ts in fields and p in fields and q in fields:
                chosen=(ts,p,q); break
        if chosen is None:
            raise RuntimeError("FAIL_CLOSED: raw trades.csv lacks an unambiguous timestamp/price/quantity schema")
        buckets={}
        for row in reader:
            ts_s,price_s,qty_s=(row[x] for x in chosen)
            try:
                ts=float(ts_s); price=float(price_s); qty=float(qty_s)
            except ValueError: continue
            minute=int(ts//60) if ts>1e11 else int(ts*1000//60000)
            b=buckets.setdefault(minute,{"t":minute,"o":price,"h":price,"l":price,"c":price,"v":0.0})
            b["h"]=max(b["h"],price); b["l"]=min(b["l"],price); b["c"]=price; b["v"]+=qty
        return [buckets[k] for k in sorted(buckets)]

def validate_definition(d,s):
    assert d["candidate_id"]=="CANDIDATE_RESEARCH_INDEPENDENT_C"
    assert d["candidate_version"]=="C-v1"
    assert d["research_only"] and not d["live_execution"] and not d["wallet_operations"] and not d["promotion"]
    assert d["evaluation"]=={**d["evaluation"],"folds":8,"train_bars":800,"test_bars":400,"step_bars":400}
    assert s["candidate_id"]==d["candidate_id"]
    assert s["active_blob"]=="eef65102d4671a43f11f9dc311e0617aa220eb64"
    assert s["integrity"]["verified_archive_count"]==12
    assert d["position_policy"]["lookahead"] is False

def main():
    d,s=load_json(DEF),load_json(SNAP)
    validate_definition(d,s)
    raw_sha=sha256_file(RAW)
    if raw_sha!=s["active_blob"]:
        raise RuntimeError(f"FAIL_CLOSED: active blob mismatch: {raw_sha}")
    bars=aggregate_1m(RAW)
    if len(bars)<8*(800+400): raise RuntimeError("FAIL_CLOSED: insufficient bars for declared 8 folds")
    closes=[x["c"] for x in bars]; highs=[x["h"] for x in bars]; lows=[x["l"] for x in bars]
    e20,e50=ema(closes,20),ema(closes,50); a14=atr(highs,lows,closes,14)
    folds=[]
    for i in range(8):
        train_start=i*400; train_end=train_start+800; test_start=train_end; test_end=test_start+400
        if test_end>len(bars): raise RuntimeError("FAIL_CLOSED: fold exceeds snapshot bar range")
        folds.append({"fold":i+1,"train":[train_start,train_end],"test":[test_start,test_end],
                      "timestamp_start":bars[test_start]["t"],"timestamp_end":bars[test_end-1]["t"]})
    artifact={
      "artifact_id":"CANDIDATE_C_OOS_EXECUTION_READY_2026-10-01",
      "status":"READY_FOR_OOS_AFTER_WORKFLOW_GATE",
      "definition_sha256":sha256_file(DEF),"snapshot_file_sha256":sha256_file(SNAP),
      "raw_blob_sha256":raw_sha,"bars_1m":len(bars),
      "features":{"ema20_ready":sum(not math.isnan(x) for x in e20),
                  "ema50_ready":sum(not math.isnan(x) for x in e50),
                  "atr14_ready":sum(not math.isnan(x) for x in a14)},
      "folds":folds,
      "rule":{"long":"close_t > prior_20_bar_high AND ema20_t > ema50_t",
              "short":"close_t < prior_20_bar_low AND ema20_t < ema50_t",
              "entry":"next_bar_open","SL_ATR":1.5,"TP_ATR":2.0,"max_holding_bars":30},
      "safety":{"research_only":True,"live_execution":False,"wallet_operations":False,"promotion":False,
                "rule_a_reuse":False,"candidate_b_reuse":False,"post_oos_tuning":False},
      "oos_started":False,"generated_at_utc":datetime.now(timezone.utc).isoformat()
    }
    print(json.dumps(artifact,indent=2))

if __name__=="__main__": main()
