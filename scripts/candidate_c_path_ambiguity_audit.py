#!/usr/bin/env python3
"""Candidate C v1 pre-execution ambiguity audit.

Research-only. This audit does NOT execute trades, score performance, or alter
the frozen candidate definition. It reconstructs the immutable snapshot and
checks whether any signal-entry position can have both SL and TP touched in
the same OHLC bar. Such a bar is path-ambiguous and must be resolved by an
explicit frozen policy before OOS execution; otherwise fail closed.
"""
import csv, hashlib, io, json, math, subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DEF = ROOT / "evidence/candidate_c_definition_v1.json"
SNAP = ROOT / "evidence/candidate_c_fresh_snapshot_20261001.json"

def load(p): return json.loads(p.read_text())

def blob_sha(raw):
    return hashlib.sha1((f"blob {len(raw)}" + chr(0)).encode() + raw).hexdigest()

def raw_from_snapshot(s):
    raw = subprocess.run(["git","cat-file","blob",s["active_blob"]],
                         cwd=ROOT, check=True, capture_output=True).stdout
    if blob_sha(raw) != s["active_blob"]:
        raise RuntimeError("FAIL_CLOSED: active snapshot blob hash mismatch")
    return raw

def parse_ts(x):
    x=x.strip()
    try:
        v=float(x)
    except ValueError:
        return datetime.fromisoformat(x.replace("Z","+00:00")).timestamp()
    # Normalize epoch seconds / milliseconds / microseconds deterministically.
    if v >= 1e15: return v/1e6
    if v >= 1e12: return v/1e3
    return v

def bars(raw):
    reader=csv.DictReader(io.StringIO(raw.decode("utf-8")))
    fields=reader.fieldnames or []
    candidates=[("timestamp","price","quantity"),("time","price","quantity"),
                ("timestamp","price","amount"),("updated","price","amount")]
    chosen=next((x for x in candidates if all(k in fields for k in x)),None)
    if not chosen: raise RuntimeError("FAIL_CLOSED: ambiguous raw schema")
    buckets={}
    for row in reader:
        try:
            t=parse_ts(row[chosen[0]])
            p=float(row[chosen[1]]); q=float(row[chosen[2]])
            if not all(math.isfinite(x) for x in (t,p,q)): continue
        except (ValueError,TypeError,OverflowError): continue
        m=int(t//60)
        b=buckets.setdefault(m,{"t":m,"o":p,"h":p,"l":p,"c":p,"v":0.0})
        b["h"]=max(b["h"],p); b["l"]=min(b["l"],p); b["c"]=p; b["v"]+=q
    return [buckets[k] for k in sorted(buckets)]

def ema(xs,n):
    a=2/(n+1); out=[xs[0]]
    for x in xs[1:]: out.append(a*x+(1-a)*out[-1])
    return out

def atr(h,l,c,n):
    tr=[]; prev=None
    for hi,lo,cl in zip(h,l,c):
        tr.append(hi-lo if prev is None else max(hi-lo,abs(hi-prev),abs(lo-prev)))
        prev=cl
    out=[math.nan]*len(tr)
    if len(tr)>=n:
        out[n-1]=sum(tr[:n])/n
        for i in range(n,len(tr)): out[i]=(out[i-1]*(n-1)+tr[i])/n
    return out

def main():
    d,s=load(DEF),load(SNAP)
    if d["candidate_version"]!="C-v1" or not d["research_only"] or d["live_execution"] or d["promotion"]:
        raise RuntimeError("FAIL_CLOSED: frozen safety contract mismatch")
    raw=raw_from_snapshot(s); b=bars(raw)
    c=[x["c"] for x in b]; h=[x["h"] for x in b]; l=[x["l"] for x in b]
    e20,e50,a14=ema(c,20),ema(c,50),atr(h,l,c,14)
    ambiguities=[]
    signals=0
    MAX_HOLD_BARS=int(d["time_exit"]["max_holding_bars"])
    for t in range(20,len(b)-1):
        prior_hi=max(h[t-20:t]); prior_lo=min(l[t-20:t])
        long_ok=c[t]>prior_hi and e20[t]>e50[t]
        short_ok=c[t]<prior_lo and e20[t]<e50[t]
        if not (long_ok or short_ok) or not math.isfinite(a14[t]) or a14[t] <= 0: continue
        entry_idx=t+1
        if entry_idx >= len(b): continue
        signals += 1
        entry=b[entry_idx]["o"]
        if long_ok:
            sl=entry-1.5*a14[t]; tp=entry+2.0*a14[t]; side="LONG"
        else:
            sl=entry+1.5*a14[t]; tp=entry-2.0*a14[t]; side="SHORT"
        end_idx=min(len(b)-1, entry_idx+MAX_HOLD_BARS-1)
        for j in range(entry_idx,end_idx+1):
            hit_sl=(b[j]["l"]<=sl) if side=="LONG" else (b[j]["h"]>=sl)
            hit_tp=(b[j]["h"]>=tp) if side=="LONG" else (b[j]["l"]<=tp)
            if hit_sl and hit_tp:
                ambiguities.append({"signal_index":t,"entry_index":entry_idx,"bar_index":j,"side":side,
                                     "signal_time":b[t]["t"],"entry_time":b[entry_idx]["t"],"ambiguous_bar_time":b[j]["t"],
                                     "entry":entry,"stop":sl,"target":tp})
                break
    artifact={
      "artifact_id":"CANDIDATE_C_PRE_OOS_PATH_AMBIGUITY_AUDIT_2026-10-01",
      "status":"BLOCKED_PENDING_EXPLICIT_SAME_BAR_EXIT_POLICY" if ambiguities else "NO_PATH_AMBIGUITY_DETECTED",
      "candidate_version":d["candidate_version"],
      "raw_blob_sha":s["active_blob"],"bars_1m":len(b),
      "candidate_signals_scanned":signals,
      "ambiguous_same_bar_sl_tp_count":len(ambiguities),
      "ambiguous_examples":ambiguities[:20],
      "oos_started":False,
      "research_only":True,"live_execution":False,"promotion":False,
      "generated_at_utc":datetime.now(timezone.utc).isoformat()
    }
    print(json.dumps(artifact,indent=2))

if __name__=="__main__": main()
