#!/usr/bin/env python3
import json,math,statistics
from collections import Counter
from pathlib import Path
FOLDS=8
FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]
EXACT=["timestamp","sequence_first","sequence_last","entry_price","exit_price","direction","gross_return"]
def smd(a,b):
    if not a or not b:return None
    va=statistics.pvariance(a) if len(a)>1 else 0; vb=statistics.pvariance(b) if len(b)>1 else 0
    d=math.sqrt((va+vb)/2)
    return (statistics.fmean(a)-statistics.fmean(b))/d if d else 0
def kish(ns):
    n=sum(ns); d=sum(x*x for x in ns); return n*n/d if d else 0
def key(r): return tuple(r.get(k) for k in EXACT)
def fold_summary(rows):
    c=Counter(r["fold_index"] for r in rows)
    return {"counts_by_fold":{str(i):c.get(i,0) for i in range(FOLDS)},
            "largest_fold":max(c,key=c.get),"largest_fold_share":max(c.values())/len(rows),
            "kish_ess":kish(list(c.values()))}
def main():
    p=json.loads(Path("prior_1049_protocol.json").read_text()); c=json.loads(Path("current_1027_protocol.json").read_text())
    ps=p["winners"]; cw=c["winners"]; assert len(ps)==14 and len(cw)==28
    pk={key(r) for r in ps}; matches=[r for r in cw if key(r) in pk]; assert not matches
    psf, cwf=fold_summary(ps),fold_summary(cw)
    feats={}
    for f in FEATURES:
        a=p["feature_contrast"][f]["smd"]; b=c["feature_contrast"][f]["smd"]
        feats[f]={"prior_smd":a,"current_smd":b,"sign_consistent":a*b>0,"min_abs_smd":min(abs(a),abs(b))}
    direction={"prior_14":dict(Counter(r["direction"] for r in ps)),"current_28":dict(Counter(r["direction"] for r in cw))}
    regime={"prior_14":dict(Counter(r["fold_regime"] for r in ps)),"current_28":dict(Counter(r["fold_regime"] for r in cw))}
    out={"status":"evidence-only","protocol":{"train":800,"test":400,"step":400,"folds":8,"gross_threshold_bps":14},
      "cross_lineage":{"current_winners":28,"prior_survivors":14,"exact_key":EXACT,"exact_matches":0,"identity_conclusion":"NO_EXACT_RECORD_IDENTITY_OVERLAP"},
      "lineage_summary":{"prior_14":{"winners":14,"folds":psf},"current_28":{"winners":28,"folds":cwf}},
      "direction_stability":direction,"regime_stability":regime,"feature_level_cross_lineage_evidence":feats,
      "effective_evidence":{"independence_unit":"lineage × temporal walk-forward test fold","prior_nominal":14,"prior_kish_ess":psf["kish_ess"],"current_nominal":28,"current_kish_ess":cwf["kish_ess"],"combined_nominal":42,"combined_kish_ess":kish([* [v for v in psf["counts_by_fold"].values() if v],* [v for v in cwf["counts_by_fold"].values() if v]]),"interpretation":"fold-based dependence diagnostic; not a statistical effective sample size estimator"},
      "concentration_sensitivity":{"fixed_unit":"temporal test fold","interpretation":"descriptive concentration diagnostic; not proof of independence"},
      "claim_boundary":{"threshold_tuned":False,"winner_reselected":False,"records_deleted":False,"feature_fitting":False,"independence_proven":False,"predictive_validity":False,"causality":False,"market_generalization":False,"promotion":False,"live_execution":False},
      "final_evidence_verdict":{"final_evidence_verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION","reason":"Exact lineage identity is reconciled, but finite observations remain dependent within temporal folds; independence, predictive validity, causality, and market generalization are not proven."}}
    Path("cross_lineage_effective_evidence_v1.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({"exact_matches":0,"prior_kish_ess":psf["kish_ess"],"current_kish_ess":cwf["kish_ess"],"combined_kish_ess":out["effective_evidence"]["combined_kish_ess"],"verdict":out["final_evidence_verdict"]["final_evidence_verdict"]},indent=2))
if __name__=="__main__": main()
