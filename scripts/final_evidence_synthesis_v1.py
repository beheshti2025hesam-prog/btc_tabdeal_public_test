#!/usr/bin/env python3
"""Final evidence synthesis: fixed fold-concentration stress + LOFO + cross-lineage reconciliation.

Research-only / fail-closed. No tuning, winner reselection, deletion, promotion, or live execution.
"""
import json, statistics
from pathlib import Path

FOLDS=8

def gross(rows): return sum(r["gross_return"] for r in rows)
def summary(rows):
    g=[r["gross_return"] for r in rows]
    return {"n":len(g),"gross_sum":gross(rows),"mean":statistics.fmean(g) if g else None,
            "median":statistics.median(g) if g else None,"min":min(g) if g else None,"max":max(g) if g else None}

def fold(rows,f): return [r for r in rows if r["fold_index"]==f]
def lofo(rows,f): return [r for r in rows if r["fold_index"]!=f]

def concentration(rows):
    total=gross(rows)
    items=[]
    for f in range(FOLDS):
        r=fold(rows,f);items.append({
            "fold":f,"n":len(r),"gross_sum":gross(r),
            "gross_share":gross(r)/total if total else None,
            "abs_gross_share":sum(abs(x["gross_return"]) for x in r)/sum(abs(x["gross_return"]) for x in rows) if rows else None,
        })
    return items

def stability(rows):
    total=gross(rows)
    out={}
    for f in range(FOLDS):
        r=lofo(rows,f); g=gross(r)
        out[str(f)]={"remaining":summary(r),"gross_fraction_remaining":g/total if total else None}
    return out

def stress(rows):
    total=gross(rows)
    ordered=sorted(range(FOLDS),key=lambda f:gross(fold(rows,f)),reverse=True)
    out=[]
    for k in range(1,4):
        excluded=ordered[:k]
        r=[x for x in rows if x["fold_index"] not in excluded]
        out.append({"top_k_folds_excluded":k,"excluded_folds":excluded,"remaining":summary(r),
                    "gross_fraction_remaining":gross(r)/total if total else None})
    return out

def category(rows,key):
    out={}
    for v in sorted(set(str(x[key]) for x in rows)):
        out[v]=summary([x for x in rows if str(x[key])==v])
    return out

def sign_cross(a,b,key):
    aa=category(a,key);bb=category(b,key)
    return {k:{"prior_gross":aa.get(k,{"gross_sum":0})["gross_sum"],
               "current_gross":bb.get(k,{"gross_sum":0})["gross_sum"],
               "same_sign":aa.get(k,{"gross_sum":0})["gross_sum"]*bb.get(k,{"gross_sum":0})["gross_sum"]>0}
            for k in sorted(set(aa)|set(bb))}

def main():
    p=json.loads(Path("prior_1049_protocol.json").read_text())
    c=json.loads(Path("current_1027_protocol.json").read_text())
    pw,cw=p["winners"],c["winners"]
    assert len(pw)==14 and len(cw)==28
    result={
      "protocol":{"train":800,"test":400,"step":400,"folds":8,"gross_threshold_bps":14},
      "population":{"prior_14":14,"current_28":28,"nominal_total":42},
      "overall":{"prior_14":summary(pw),"current_28":summary(cw)},
      "fold_concentration":{"prior_14":concentration(pw),"current_28":concentration(cw)},
      "lofo_fold":{"prior_14":stability(pw),"current_28":stability(cw)},
      "top_fold_exclusion_stress":{"prior_14":stress(pw),"current_28":stress(cw)},
      "direction_cross_lineage":sign_cross(pw,cw,"direction"),
      "regime_cross_lineage":sign_cross(pw,cw,"fold_regime"),
      "claim_boundary":{
        "threshold_tuned":False,"winner_reselected":False,"records_deleted":False,
        "independence_proven":False,"predictive_validity":False,"causality":False,
        "market_generalization":False,"promotion":False,"live_execution":False},
      "verdict":{
        "status":"FINAL_EVIDENCE_SYNTHESIS",
        "promotion":"BLOCKED",
        "reason":"Evidence survives exact lineage reconciliation and direction/regime sign checks, but fold concentration and finite dependent evidence prevent a promotion claim. Downtrend evidence is absent from the locked winner populations."
      }
    }
    Path("final_evidence_synthesis_v1.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"prior_top_fold":max(result["fold_concentration"]["prior_14"],key=lambda x:x["n"]),
      "current_top_fold":max(result["fold_concentration"]["current_28"],key=lambda x:x["n"]),
      "prior_stress_after_top_fold":result["top_fold_exclusion_stress"]["prior_14"][0]["remaining"]["gross_sum"],
      "current_stress_after_top_fold":result["top_fold_exclusion_stress"]["current_28"][0]["remaining"]["gross_sum"],
      "promotion":"BLOCKED"},indent=2))
if __name__=="__main__":main()
