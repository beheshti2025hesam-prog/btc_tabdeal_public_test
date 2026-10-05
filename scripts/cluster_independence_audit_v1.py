#!/usr/bin/env python3
import json, math, statistics
from pathlib import Path

FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]
THRESHOLDS=[0.5,1.0,1.5,2.0]

def dist(a,b,mu,sd):
    return math.sqrt(sum(((a[f]-b[f])/sd[f])**2 for f in FEATURES))

def components(rows,threshold,mu,sd):
    n=len(rows); p=list(range(n))
    def find(x):
        while p[x]!=x:
            p[x]=p[p[x]]; x=p[x]
        return x
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:p[b]=a
    for i in range(n):
        for j in range(i+1,n):
            if dist(rows[i],rows[j],mu,sd)<=threshold: union(i,j)
    g={}
    for i in range(n): g.setdefault(find(i),[]).append(i)
    return list(g.values())

def effective_cluster_count(sizes):
    n=sum(sizes)
    return (n*n/sum(x*x for x in sizes)) if sizes else 0.0

def pooled_moments(snapshot):
    # Reconstruct frozen Winner+Control population moments from locked summary statistics.
    mu={}; sd={}
    for f in FEATURES:
        w=snapshot["feature_contrast"][f]["winners"]
        c=snapshot["feature_contrast"][f]["controls"]
        n=w["n"]+c["n"]
        mean=(w["n"]*w["mean"]+c["n"]*c["mean"])/n
        # population second central moment from group sample variances
        ss=(w["n"]*(w["std"]**2*(w["n"]-1)/w["n"] + (w["mean"]-mean)**2)
            +c["n"]*(c["std"]**2*(c["n"]-1)/c["n"] + (c["mean"]-mean)**2))
        mu[f]=mean
        sd[f]=math.sqrt(ss/n) or 1.0
    return mu,sd

def audit(snapshot,label,mu,sd):
    winners=snapshot["winners"]
    out={}
    for t in THRESHOLDS:
        cs=components(winners,t,mu,sd)
        sizes=sorted([len(c) for c in cs],reverse=True)
        out[str(t)]={"winner_clusters":len(cs),
                     "largest_winner_cluster":sizes[0] if sizes else 0,
                     "effective_winner_cluster_count":effective_cluster_count(sizes),
                     "cluster_sizes":sizes}
    return {"label":label,"winners":len(winners),"thresholds":out}

def load(path): return json.loads(Path(path).read_text())

def main():
    prior=load("prior_1049_protocol.json")
    current=load("current_1027_protocol.json")
    combined_for_scale=prior["feature_contrast"]
    # Reconstruct pooled moments using both frozen snapshots, weighted by their locked counts.
    mu={}; sd={}
    for f in FEATURES:
        p=prior["feature_contrast"][f]; q=current["feature_contrast"][f]
        groups=[]
        for g in (p,q):
            groups.extend([g["winners"],g["controls"]])
        n=sum(g["n"] for g in groups)
        mean=sum(g["n"]*g["mean"] for g in groups)/n
        ss=sum(g["n"]*(g["std"]**2*(g["n"]-1)/g["n"]+(g["mean"]-mean)**2) for g in groups)
        mu[f]=mean; sd[f]=math.sqrt(ss/n) or 1.0
    out={"protocol":"cluster-independence-protocol-v1",
         "prior_14":audit(prior,"prior_14",mu,sd),
         "current_28":audit(current,"current_28",mu,sd),
         "standardization":"pooled frozen Winner+Control summary moments across prior and current snapshots",
         "claim_boundary":{"threshold_selection":"fixed pre-registered sensitivity set",
           "independence_proven":False,"predictive_validity":False,"causality":False,
           "market_generalization":False,"promotion":"BLOCKED"},
         "final_verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION"}
    Path("cluster_independence_audit_v1.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
