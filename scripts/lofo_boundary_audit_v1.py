#!/usr/bin/env python3
import json, math, statistics
from pathlib import Path
from collections import Counter

FOLDS = 8
FEATURES = ["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]

def smd(a,b):
    if not a or not b: return None
    va = statistics.pvariance(a) if len(a)>1 else 0
    vb = statistics.pvariance(b) if len(b)>1 else 0
    d = math.sqrt((va+vb)/2)
    return (statistics.fmean(a)-statistics.fmean(b))/d if d else 0.0

def sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0

def audit(d):
    winners=d["winners"]
    # Reconstruct controls only through fold/categorical counts is insufficient; the frozen
    # snapshot is intentionally represented by the already materialized protocol JSON.
    # Therefore use the protocol's fold-exclusion SMD as the immutable LOFO primitive.
    out={}
    for f in FEATURES:
        full=d["feature_contrast"][f]["smd"]
        vals={}
        for fold in range(FOLDS):
            x=d["stability"]["fold_exclusion"].get(str(fold),{})
            vals[str(fold)]=x.get("feature_smd_without_fold")
        clean=[v[f] for v in vals.values() if isinstance(v,dict) and v.get(f) is not None]
        out[f]={
            "full_smd":full,
            "loo_smd":[v[f] for v in vals.values() if isinstance(v,dict) and v.get(f) is not None],
            "same_sign_full_and_all_loo": bool(clean) and sign(full)!=0 and all(sign(x)==sign(full) for x in clean),
            "min_abs_loo_smd": min((abs(x) for x in clean), default=None),
        }
    # A true fold-LOFO claim is stronger than the prior descriptive label:
    # every retained fold exclusion must preserve feature contrast sign.
    supported=Counter(w["fold_index"] for w in winners)
    dominant=max(supported, key=supported.get)
    dominant_share=supported[dominant]/len(winners)
    return {
      "status":"evidence-only",
      "population":{"winners":len(winners),"supported_folds":len(supported)},
      "winner_fold_counts":dict(supported),
      "concentration":{"dominant_fold":dominant,"dominant_share":dominant_share},
      "feature_lofo":out,
      "claim_boundary":{
        "threshold_tuned":False,"parameter_tuning":False,"model_fitting":False,
        "promotion":False,"live_execution":False
      },
      "verdict":{
        "lofo":"PASS_DESCRIPTIVE" if all(v["same_sign_full_and_all_loo"] for v in out.values()) else "FAIL_DESCRIPTIVE",
        "concentration":"REQUIRES_REVIEW" if dominant_share >= 0.5 else "DESCRIPTIVE",
        "promotion":"BLOCKED"
      }
    }

def main():
    prior=json.loads(Path("prior_1049_protocol.json").read_text())
    current=json.loads(Path("current_1027_protocol.json").read_text())
    result={"prior_14":audit(prior),"current_28":audit(current),
            "final_verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION"}
    Path("lofo_boundary_audit_v1.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
