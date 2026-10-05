#!/usr/bin/env python3
import json, math, statistics
from collections import Counter
from pathlib import Path
FOLDS=8
FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]
EXACT=["timestamp","sequence_first","sequence_last","entry_price","exit_price","direction","gross_return"]
def smd(a,b):
    if not a or not b:return None
    va=statistics.pvariance(a) if len(a)>1 else 0; vb=statistics.pvariance(b) if len(b)>1 else 0
    d=math.sqrt((va+vb)/2); return (statistics.fmean(a)-statistics.fmean(b))/d if d else 0.0
def kish(ns):
    n=sum(ns); d=sum(x*x for x in ns); return n*n/d if d else 0.0
def key(r): return tuple(r.get(k) for k in EXACT)
def lofo(rows):
    o={}
    for f in range(FOLDS):
        k=[r for r in rows if r["fold_index"]!=f]
        o[str(f)]={"excluded":len(rows)-len(k),"remaining":len(k),"supported_folds":len(set(r["fold_index"] for r in k)),"gross_sum":sum(r["gross_return"] for r in k),"direction":dict(Counter(r["direction"] for r in k)),"regime":dict(Counter(r["fold_regime"] for r in k))}
    return o
def conc(rows):
    c=Counter(r["fold_index"] for r in rows); counts={str(i):c.get(i,0) for i in range(FOLDS)}
    return {"counts_by_fold":counts,"largest_fold":max(c,key=c.get),"largest_fold_share":max(c.values())/len(rows),"kish_ess":kish(list(c.values())),"without_each_fold":{str(f):{"remaining":sum(r["fold_index"]!=f for r in rows),"gross_sum":sum(r["gross_return"] for r in rows if r["fold_index"]!=f),"supported_folds":len({r["fold_index"] for r in rows if r["fold_index"]!=f})} for f in c}}
def main():
    p=json.loads(Path("prior_1049_protocol.json").read_text()); c=json.loads(Path("current_1027_protocol.json").read_text())
    ps=p["winners"]; cw=c["winners"]; assert len(ps)==14 and len(cw)==28
    pk={key(r) for r in ps}; matches=[r for r in cw if key(r) in pk]
    pc=conc(ps); cc=conc(cw); plo=lofo(ps); clo=lofo(cw)
    fs={}
    for name,d in [("prior_14",p),("current_28",c)]:
        fs[name]={}
        for f in FEATURES:
            vals={str(i):d["stability"]["fold_exclusion"].get(str(i),{}).get("feature_smd_without_fold",{}).get(f) for i in range(FOLDS)}
            clean=[v for v in vals.values() if v is not None]
            full=d["feature_contrast"][f]["smd"]
            fs[name][f]={"full_smd":full,"loo_smd":vals,"same_sign_all":bool(clean) and len({1 if v>0 else -1 if v<0 else 0 for v in clean})==1 and (1 if full>0 else -1 if full<0 else 0)==(1 if clean[0]>0 else -1 if clean[0]<0 else 0)}
    a=[v for v in cc["counts_by_fold"].values() if v]; b=[v for v in pc["counts_by_fold"].values() if v]
    eff={"independence_unit":"lineage × temporal walk-forward test fold","current_nominal":28,"current_kish_ess":cc["kish_ess"],"prior_nominal":14,"prior_kish_ess":pc["kish_ess"],"combined_nominal":42,"combined_kish_ess":kish(a+b),"current_supported_folds":len(a),"prior_supported_folds":len(b),"exact_cross_lineage_matches":len(matches)}
    cd=cc["largest_fold"]; pd=pc["largest_fold"]
    verdict={"cross_lineage_reconciliation":"PASS" if not matches else "FAIL","cluster_independence":"CAUTION","lofo":"PASS_DESCRIPTIVE","direction_stability":"DESCRIPTIVE_ONLY","regime_stability":"DESCRIPTIVE_ONLY","concentration_sensitivity":"REQUIRES_REVIEW","effective_evidence":"LIMITED","final_evidence_verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION","reason":"The 28 current Winners and 14 prior Survivors are exact-nonmatching, but nominal observations are clustered in temporal folds; effective evidence must use lineage×fold units.","forbidden_actions":["delete winners","change threshold","tune","rewrite locked artifacts","v2 execution","live execution"]}
    out={"status":"evidence-only","protocol":{"train":800,"test":400,"step":400,"folds":8,"gross_threshold_bps":14},"cross_lineage":{"current_winners":28,"prior_survivors":14,"exact_key":EXACT,"exact_matches":len(matches),"prior_unmatched":14-len(matches)},"cluster_independence":{"current_28":cc,"prior_14":pc},"lofo":{"current_28":clo,"prior_14":plo},"direction_stability":{"current_28_full":dict(Counter(r["direction"] for r in cw)),"prior_14_full":dict(Counter(r["direction"] for r in ps)),"current_28_lofo":clo,"prior_14_lofo":plo},"regime_stability":{"current_28_full":dict(Counter(r["fold_regime"] for r in cw)),"prior_14_full":dict(Counter(r["fold_regime"] for r in ps)),"current_28_lofo":clo,"prior_14_lofo":plo},"feature_stability":fs,"cross_lineage_feature_smd":{f:smd([r[f] for r in cw],[r[f] for r in ps]) for f in FEATURES},"concentration_sensitivity":{"current_dominant_fold":cd,"current_without_dominant":cc["without_each_fold"][str(cd)],"prior_dominant_fold":pd,"prior_without_dominant":pc["without_each_fold"][str(pd)]},"effective_evidence":eff,"final_evidence_verdict":verdict,"claim_boundary":{"signal_created":False,"threshold_tuned":False,"parameter_tuning":False,"model_fitting":False,"promotion":False,"live_execution":False}}
    Path("cross_lineage_effective_evidence_v1.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({"exact_matches":len(matches),"current_ess":cc["kish_ess"],"prior_ess":pc["kish_ess"],"combined_ess":eff["combined_kish_ess"],"verdict":verdict["final_evidence_verdict"]},indent=2))
if __name__=="__main__":main()
