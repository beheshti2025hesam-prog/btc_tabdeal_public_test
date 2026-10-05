#!/usr/bin/env python3
"""Fail-closed Direction × Regime × Fold stability audit.

Evidence-only. Uses the immutable 8-fold / 800-400-400 / >14bps protocol.
No threshold tuning, winner reselection, deletion, fitting, or promotion.
"""
import json, statistics
from collections import Counter
from pathlib import Path

FOLDS=8

def q(v,p):
    if not v:return None
    s=sorted(v);x=(len(s)-1)*p;lo=int(x);hi=min(lo+1,len(s)-1)
    return s[lo]+(s[hi]-s[lo])*(x-lo)

def stats(rows):
    g=[r["gross_return"] for r in rows]
    return {
        "n":len(g),"gross_sum":sum(g),
        "mean":statistics.fmean(g) if g else None,
        "median":statistics.median(g) if g else None,
        "q25":q(g,.25),"q75":q(g,.75),
        "min":min(g) if g else None,"max":max(g) if g else None,
    }

def category(rows,key):
    out={}
    for value in sorted(set(str(r[key]) for r in rows)):
        rs=[r for r in rows if str(r[key])==value]
        out[value]=stats(rs)
    return out

def fold_stability(rows):
    out={}
    n=len(rows)
    for fold in range(FOLDS):
        rs=[r for r in rows if r["fold_index"]==fold]
        out[str(fold)]=stats(rs)|{
            "share_of_winners":len(rs)/n if n else 0,
            "share_of_gross_abs":sum(abs(r["gross_return"]) for r in rs)/sum(abs(r["gross_return"]) for r in rows) if rows else 0,
        }
    return out

def lofo(rows):
    total=sum(r["gross_return"] for r in rows)
    out={}
    for fold in range(FOLDS):
        rs=[r for r in rows if r["fold_index"]!=fold]
        out[str(fold)]={
            "remaining_winners":len(rs),
            "remaining_gross_sum":sum(r["gross_return"] for r in rs),
            "gross_fraction_remaining":sum(r["gross_return"] for r in rs)/total if total else None,
        }
    return out

def sign_consistency(a,b,key):
    av={k:v["gross_sum"] for k,v in category(a,key).items()}
    bv={k:v["gross_sum"] for k,v in category(b,key).items()}
    keys=sorted(set(av)|set(bv))
    return {k:{"prior_gross_sum":av.get(k,0),"current_gross_sum":bv.get(k,0),
               "same_sign":(av.get(k,0)==0 or bv.get(k,0)==0 or av.get(k,0)*bv.get(k,0)>0)}
            for k in keys}

def audit(snapshot,label):
    w=snapshot["winners"]
    return {
        "label":label,"winner_count":len(w),
        "overall":stats(w),
        "fold":fold_stability(w),
        "direction":category(w,"direction"),
        "regime":category(w,"fold_regime"),
        "lofo_fold":lofo(w),
        "coverage":{
            "folds_with_winners":sum(bool([r for r in w if r["fold_index"]==f]) for f in range(FOLDS)),
            "folds_total":FOLDS,
            "directions_present":sorted(set(r["direction"] for r in w)),
            "regimes_present":sorted(set(r["fold_regime"] for r in w)),
        },
    }

def main():
    prior=json.loads(Path("prior_1049_protocol.json").read_text())
    current=json.loads(Path("current_1027_protocol.json").read_text())
    assert len(prior["winners"])==14 and len(current["winners"])==28
    pa=audit(prior,"prior_14")
    ca=audit(current,"current_28")
    result={
      "protocol":{"train":800,"test":400,"step":400,"folds":8,"gross_threshold_bps":14},
      "populations":{"prior_14":14,"current_28":28},
      "prior":pa,"current":ca,
      "cross_lineage_stability":{
        "direction":sign_consistency(prior["winners"],current["winners"],"direction"),
        "regime":sign_consistency(prior["winners"],current["winners"],"fold_regime"),
      },
      "robustness_flags":{
        "prior_all_folds_represented":pa["coverage"]["folds_with_winners"]==FOLDS,
        "current_all_folds_represented":ca["coverage"]["folds_with_winners"]==FOLDS,
        "prior_both_directions_present":len(pa["coverage"]["directions_present"])>1,
        "current_both_directions_present":len(ca["coverage"]["directions_present"])>1,
        "prior_multiple_regimes_present":len(pa["coverage"]["regimes_present"])>1,
        "current_multiple_regimes_present":len(ca["coverage"]["regimes_present"])>1,
      },
      "claim_boundary":{
        "threshold_tuned":False,"winner_reselected":False,"records_deleted":False,
        "independence_proven":False,"predictive_validity":False,"causality":False,
        "market_generalization":False,"promotion":False,"live_execution":False,
      },
      "verdict":{
        "status":"STABILITY_DIAGNOSTIC_ONLY",
        "promotion":"BLOCKED",
        "reason":"Direction, regime and fold coverage/concentration are descriptive stability evidence; they do not establish independence, predictive validity, causality, or market generalization."
      }
    }
    Path("direction_regime_fold_stability_v1.json").write_text(json.dumps(result,indent=2)+"\n")
    def compact(x):
        return {
          "fold_counts":{k:v["n"] for k,v in x["fold"].items()},
          "fold_gross":{k:v["gross_sum"] for k,v in x["fold"].items()},
          "direction_counts":{k:v["n"] for k,v in x["direction"].items()},
          "direction_gross":{k:v["gross_sum"] for k,v in x["direction"].items()},
          "regime_counts":{k:v["n"] for k,v in x["regime"].items()},
          "regime_gross":{k:v["gross_sum"] for k,v in x["regime"].items()},
          "lofo_remaining_gross":{k:v["remaining_gross_sum"] for k,v in x["lofo_fold"].items()}
        }
    print(json.dumps({
      "prior_winners":14,"current_winners":28,
      "prior":compact(pa),"current":compact(ca),
      "cross_lineage_direction":result["cross_lineage_stability"]["direction"],
      "cross_lineage_regime":result["cross_lineage_stability"]["regime"],
      "promotion":"BLOCKED"
    },indent=2))

if __name__=="__main__":main()
