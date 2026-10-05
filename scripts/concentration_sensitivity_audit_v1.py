#!/usr/bin/env python3
import json, math
from pathlib import Path
FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]
THRESHOLDS=[0.5,1.0,1.5,2.0]
def dist(a,b,mu,sd): return math.sqrt(sum(((a[f]-b[f])/sd[f])**2 for f in FEATURES))
def components(rows,t,mu,sd):
    n=len(rows); p=list(range(n))
    def find(x):
        while p[x]!=x: p[x]=p[p[x]]; x=p[x]
        return x
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:p[b]=a
    for i in range(n):
        for j in range(i+1,n):
            if dist(rows[i],rows[j],mu,sd)<=t: union(i,j)
    g={}
    for i in range(n): g.setdefault(find(i),[]).append(i)
    return list(g.values())
def pooled_scale(prior,current):
    mu={}; sd={}
    for f in FEATURES:
        groups=[]
        for snap in (prior,current):
            groups += [snap["feature_contrast"][f]["winners"],snap["feature_contrast"][f]["controls"]]
        n=sum(g["n"] for g in groups); mean=sum(g["n"]*g["mean"] for g in groups)/n
        ss=sum(g["n"]*(g["std"]**2*(g["n"]-1)/g["n"]+(g["mean"]-mean)**2) for g in groups)
        mu[f]=mean; sd[f]=math.sqrt(ss/n) or 1.0
    return mu,sd
def audit(snapshot,label,mu,sd):
    rows=snapshot["winners"]; n=len(rows); by_t={}
    for t in THRESHOLDS:
        sizes=sorted((len(c) for c in components(rows,t,mu,sd)),reverse=True)
        ess=n*n/sum(x*x for x in sizes) if sizes else 0.0; largest=sizes[0] if sizes else 0
        by_t[str(t)]={"winner_count":n,"cluster_count":len(sizes),"largest_cluster":largest,
          "largest_cluster_share":largest/n if n else 0.0,"effective_cluster_count":ess,
          "effective_cluster_ratio":ess/n if n else 0.0,"cluster_sizes":sizes}
    vals=list(by_t.values())
    return {"label":label,"thresholds":by_t,"sensitivity":{
      "effective_cluster_count_min":min(x["effective_cluster_count"] for x in vals),
      "effective_cluster_count_max":max(x["effective_cluster_count"] for x in vals),
      "effective_cluster_ratio_min":min(x["effective_cluster_ratio"] for x in vals),
      "effective_cluster_ratio_max":max(x["effective_cluster_ratio"] for x in vals),
      "largest_cluster_share_min":min(x["largest_cluster_share"] for x in vals),
      "largest_cluster_share_max":max(x["largest_cluster_share"] for x in vals)}}
def main():
    prior=json.loads(Path("prior_1049_protocol.json").read_text()); current=json.loads(Path("current_1027_protocol.json").read_text())
    mu,sd=pooled_scale(prior,current)
    out={"protocol":"concentration-sensitivity-protocol-v1","locked_thresholds":THRESHOLDS,
      "standardization":"pooled frozen Winner+Control summary moments across prior and current snapshots",
      "prior_14":audit(prior,"prior_14",mu,sd),"current_28":audit(current,"current_28",mu,sd),
      "claim_boundary":{"dependence_diagnostic_only":True,"independence_proven":False,"predictive_validity":False,
        "causality":False,"market_generalization":False,"promotion":"BLOCKED"},
      "final_verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION"}
    Path("concentration_sensitivity_audit_v1.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
