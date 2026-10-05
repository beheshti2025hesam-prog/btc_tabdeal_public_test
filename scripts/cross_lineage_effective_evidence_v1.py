#!/usr/bin/env python3
import json,math,statistics
from collections import Counter
from pathlib import Path
FOLDS=8
FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]
THRESHOLDS=[0.5,1.0,1.5,2.0]
KEY=["timestamp","sequence_first","sequence_last","entry_price","exit_price","direction","gross_return"]
def kish(ns):
    n=sum(ns);d=sum(x*x for x in ns);return n*n/d if d else 0.0
def key(r):return tuple(r.get(k) for k in KEY)
def scale(a,b):
    mu={};sd={}
    for f in FEATURES:
        gs=[a["feature_contrast"][f]["winners"],a["feature_contrast"][f]["controls"],b["feature_contrast"][f]["winners"],b["feature_contrast"][f]["controls"]]
        n=sum(g["n"] for g in gs);m=sum(g["n"]*g["mean"] for g in gs)/n
        ss=sum(g["n"]*(g["std"]**2*(g["n"]-1)/g["n"]+(g["mean"]-m)**2) for g in gs)
        mu[f]=m;sd[f]=math.sqrt(ss/n) or 1.0
    return mu,sd
def clusters(rows,t,mu,sd):
    p=list(range(len(rows)))
    def find(x):
        while p[x]!=x:p[x]=p[p[x]];x=p[x]
        return x
    for i in range(len(rows)):
        for j in range(i+1,len(rows)):
            d=math.sqrt(sum(((rows[i][f]-rows[j][f])/sd[f])**2 for f in FEATURES))
            if d<=t:
                a,b=find(i),find(j)
                if a!=b:p[b]=a
    g={}
    for i in range(len(rows)):g.setdefault(find(i),[]).append(i)
    return [len(x) for x in g.values()]
def concentration(s,mu,sd):
    rows=s["winners"];n=len(rows);out={}
    for t in THRESHOLDS:
        z=sorted(clusters(rows,t,mu,sd),reverse=True)
        e=n*n/sum(x*x for x in z)
        out[str(t)]={"winner_count":n,"cluster_count":len(z),"largest_cluster":z[0],"largest_cluster_share":z[0]/n,"effective_cluster_count":e,"effective_cluster_ratio":e/n,"cluster_sizes":z}
    vals=list(out.values())
    return {"thresholds":out,"effective_cluster_count_min":min(v["effective_cluster_count"] for v in vals),"effective_cluster_count_max":max(v["effective_cluster_count"] for v in vals)}
def feature_matrix(a,b):
    out={}
    for f in FEATURES:
        x=a["feature_contrast"][f]["smd"];y=b["feature_contrast"][f]["smd"]
        out[f]={"prior_smd":x,"current_smd":y,"sign_consistent":x*y>0,"min_abs_smd":min(abs(x),abs(y))}
    return out
def main():
    p=json.loads(Path("prior_1049_protocol.json").read_text());c=json.loads(Path("current_1027_protocol.json").read_text())
    pw,cw=p["winners"],c["winners"];assert len(pw)==14 and len(cw)==28
    pk={key(r) for r in pw};matches=[r for r in cw if key(r) in pk];assert len(matches)==0
    mu,sd=scale(p,c);pc=concentration(p,mu,sd);cc=concentration(c,mu,sd)
    pmin,cmin=pc["effective_cluster_count_min"],cc["effective_cluster_count_min"]
    folds={"prior_14":dict(Counter(r["fold_index"] for r in pw)),"current_28":dict(Counter(r["fold_index"] for r in cw))}
    direction={"prior_14":dict(Counter(r["direction"] for r in pw)),"current_28":dict(Counter(r["direction"] for r in cw))}
    regime={"prior_14":dict(Counter(r["fold_regime"] for r in pw)),"current_28":dict(Counter(r["fold_regime"] for r in cw))}
    out={"status":"evidence-only","protocol":{"train":800,"test":400,"step":400,"folds":8,"gross_threshold_bps":14},
      "cross_lineage":{"current_winners":28,"prior_survivors":14,"exact_key":KEY,"exact_matches":0,"exact_current_winner_to_prior_survivor_matches":0,"identity_conclusion":"NO_EXACT_RECORD_IDENTITY_OVERLAP"},
      "lineage_summary":{"prior_14":{"winners":14,"fold_counts":folds["prior_14"]},"current_28":{"winners":28,"fold_counts":folds["current_28"]}},
      "direction_stability":direction,"regime_stability":regime,
      "feature_level_cross_lineage_evidence":feature_matrix(p,c),
      "cluster_independence":{"fixed_sensitivity_thresholds":THRESHOLDS,"prior_14":pc,"current_28":cc,"independence_proven":False},
      "concentration_sensitivity":{"prior_min_effective_cluster_count":pmin,"current_min_effective_cluster_count":cmin,"conservative_combined_proxy":pmin+cmin,"interpretation":"minimum effective cluster count across fixed pre-registered feature-distance sensitivity thresholds; dependence-adjusted proxy, not statistical ESS"},
      "effective_evidence":{"nominal_records":42,"conservative_effective_evidence_proxy":pmin+cmin,"prior_effective_min":pmin,"current_effective_min":cmin,"interpretation":"conservative dependence-adjusted evidence proxy; not a statistical effective sample size estimator"},
      "claim_boundary":{"threshold_tuned":False,"winner_reselected":False,"records_deleted":False,"feature_fitting":False,"independence_proven":False,"predictive_validity":False,"causality":False,"market_generalization":False,"promotion":False,"live_execution":False},
      "final_evidence_verdict":{"final_evidence_verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION","reason":"Identity reconciliation is closed. Dependence diagnostics reduce effective evidence; independence, predictive validity, causality, and market generalization remain unproven."}}
    Path("cross_lineage_effective_evidence_v1.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({"exact_matches":0,"prior_min_effective_cluster_count":pmin,"current_min_effective_cluster_count":cmin,"conservative_combined_proxy":pmin+cmin,"verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION"},indent=2))
if __name__=="__main__":main()
